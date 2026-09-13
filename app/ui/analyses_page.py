import json

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlmodel import select

from app.database import new_session
from app.models import Analysis, Job
from app.services.application_service import create_application
from app.ui.dialogs import AnalysisDetailsDialog


class AnalysesPage(QWidget):
    def __init__(self, on_changed=None):
        super().__init__()
        self.on_changed = on_changed
        self.analysis_ids: list[int] = []
        self.details_button = QPushButton("Ver detalhes")
        self.create_button = QPushButton("Criar candidatura")
        self.create_button.setObjectName("PrimaryButton")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Vaga", "Empresa", "Score", "Nível", "Vale aplicar", "Canal", "Recomendação"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.details_button.clicked.connect(self.show_details)
        self.create_button.clicked.connect(self.create_application)

        top = QHBoxLayout()
        top.addWidget(self.details_button)
        top.addWidget(self.create_button)
        top.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        self.analysis_ids.clear()
        with new_session() as session:
            rows = session.exec(select(Analysis, Job).join(Job).order_by(Analysis.created_at.desc())).all()
            self.table.setRowCount(len(rows))
            for row, (analysis, job) in enumerate(rows):
                self.analysis_ids.append(analysis.id)
                values = [
                    job.title,
                    job.company,
                    str(analysis.score),
                    analysis.match_level,
                    "sim" if analysis.worth_applying else "não",
                    job.channel,
                    analysis.recommendation[:160],
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value or ""))

    def _selected_analysis_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.analysis_ids):
            return None
        return self.analysis_ids[row]

    def show_details(self) -> None:
        analysis_id = self._selected_analysis_id()
        if not analysis_id:
            QMessageBox.warning(self, "Selecione uma análise", "Escolha uma análise para ver detalhes.")
            return
        with new_session() as session:
            analysis = session.get(Analysis, analysis_id)
            job = session.get(Job, analysis.job_id) if analysis else None
            if not analysis or not job:
                QMessageBox.warning(self, "Análise não encontrada", "Não foi possível carregar a análise.")
                return
            content = "\n\n".join(
                [
                    f"Vaga: {job.title} - {job.company}",
                    f"Score: {analysis.score} ({analysis.match_level})",
                    f"Pontos fortes:\n{_json_lines(analysis.strengths_json)}",
                    f"Pontos fracos:\n{_json_lines(analysis.weaknesses_json)}",
                    f"Palavras-chave:\n{_json_lines(analysis.keywords_json)}",
                    f"Requisitos faltantes:\n{_json_lines(analysis.missing_requirements_json)}",
                    f"Ajustes no currículo:\n{_json_lines(analysis.resume_adjustments_json)}",
                    f"Recomendação:\n{analysis.recommendation}",
                    f"Carta / e-mail:\nAssunto: {analysis.email_subject}\n\n{analysis.email_body}",
                    f"Ação sugerida:\n{analysis.action_suggestion}",
                ]
            )
        AnalysisDetailsDialog("Detalhes da análise", content, self).exec()

    def create_application(self) -> None:
        analysis_id = self._selected_analysis_id()
        if not analysis_id:
            QMessageBox.warning(self, "Selecione uma análise", "Escolha uma análise para criar candidatura.")
            return
        try:
            with new_session() as session:
                application = create_application(session, analysis_id)
            QMessageBox.information(self, "Candidatura criada", f"Candidatura #{application.id} criada com status {application.status}.")
            if self.on_changed:
                self.on_changed()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao criar candidatura", str(exc))


def _json_lines(value: str) -> str:
    try:
        items = json.loads(value or "[]")
    except json.JSONDecodeError:
        items = []
    return "\n".join(f"- {item}" for item in items) if items else "-"
