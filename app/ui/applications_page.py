import webbrowser

from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from sqlmodel import select

from app.database import new_session
from app.models import Analysis, Application, Job
from app.services.application_service import send_application


class ApplicationsPage(QWidget):
    def __init__(self, on_changed=None):
        super().__init__()
        self.on_changed = on_changed
        self.application_ids: list[int] = []
        self.send_button = QPushButton("Enviar e-mail")
        self.send_button.setObjectName("PrimaryButton")
        self.open_button = QPushButton("Abrir link")
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Vaga", "Empresa", "Status", "Canal", "E-mail", "Enviado em", "URL", "Notas"])
        self.table.horizontalHeader().setStretchLastSection(True)

        self.send_button.clicked.connect(self.send_selected)
        self.open_button.clicked.connect(self.open_link)

        top = QHBoxLayout()
        top.addWidget(self.send_button)
        top.addWidget(self.open_button)
        top.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        self.application_ids.clear()
        with new_session() as session:
            rows = session.exec(
                select(Application, Job, Analysis)
                .join(Job, Application.job_id == Job.id)
                .join(Analysis, Application.analysis_id == Analysis.id)
                .order_by(Application.created_at.desc())
            ).all()
            self.table.setRowCount(len(rows))
            for row, (application, job, analysis) in enumerate(rows):
                self.application_ids.append(application.id)
                values = [
                    job.title,
                    job.company,
                    application.status,
                    application.channel,
                    application.sent_to,
                    application.sent_at.isoformat(sep=" ", timespec="minutes") if application.sent_at else "",
                    job.url,
                    application.notes or analysis.action_suggestion[:100],
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value or ""))

    def _selected_application_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.application_ids):
            return None
        return self.application_ids[row]

    def send_selected(self) -> None:
        application_id = self._selected_application_id()
        if not application_id:
            QMessageBox.warning(self, "Selecione uma candidatura", "Escolha uma candidatura para enviar.")
            return
        try:
            with new_session() as session:
                application = session.get(Application, application_id)
                if application and application.channel == "sensitive_platform":
                    raise RuntimeError("Esta vaga está em plataforma sensível. Abra o link e candidate-se manualmente.")
                if application and application.channel != "email_auto":
                    raise RuntimeError("Esta candidatura precisa de revisão manual antes de qualquer envio.")
                send_application(session, application_id)
            QMessageBox.information(self, "E-mail enviado", "Candidatura enviada e registrada no histórico.")
            self.refresh()
            if self.on_changed:
                self.on_changed()
        except Exception as exc:
            QMessageBox.critical(self, "Envio bloqueado", str(exc))

    def open_link(self) -> None:
        application_id = self._selected_application_id()
        if not application_id:
            QMessageBox.warning(self, "Selecione uma candidatura", "Escolha uma candidatura para abrir.")
            return
        with new_session() as session:
            application = session.get(Application, application_id)
            job = session.get(Job, application.job_id) if application else None
            if not job or not job.url:
                QMessageBox.warning(self, "Sem link", "Esta vaga não possui URL.")
                return
            webbrowser.open(job.url)
