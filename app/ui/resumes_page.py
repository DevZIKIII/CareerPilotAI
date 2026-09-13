import json
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlmodel import select

from app.config import RESUMES_DIR
from app.database import new_session
from app.models import Resume
from app.services.resume_enhancer import safe_enhance_resume
from app.services.resume_reader import extract_basic_skills, extract_text_from_file, summarize_resume


class ResumeEnhanceWorker(QObject):
    finished = Signal(int, str, list, str)

    def __init__(self, resume_id: int, raw_text: str):
        super().__init__()
        self.resume_id = resume_id
        self.raw_text = raw_text

    def run(self) -> None:
        summary, skills, error = safe_enhance_resume(self.raw_text)
        self.finished.emit(self.resume_id, summary, skills, error or "")


class ResumesPage(QWidget):
    def __init__(self, on_changed=None):
        super().__init__()
        self.on_changed = on_changed
        self.resume_ids: list[int] = []
        self.thread: QThread | None = None
        self.worker: ResumeEnhanceWorker | None = None
        self.import_button = QPushButton("Importar currículo")
        self.import_button.setObjectName("PrimaryButton")
        self.primary_button = QPushButton("Definir como currículo principal")
        self.enhance_button = QPushButton("Estruturar com IA")
        self.list_widget = QListWidget()
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)

        self.import_button.clicked.connect(self.import_resume)
        self.primary_button.clicked.connect(self.set_primary)
        self.enhance_button.clicked.connect(self.enhance_selected)
        self.list_widget.currentRowChanged.connect(self.show_preview)

        buttons = QHBoxLayout()
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.enhance_button)
        buttons.addWidget(self.primary_button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        body = QHBoxLayout()
        body.addWidget(self.list_widget, 1)
        body.addWidget(self.preview, 2)
        layout.addLayout(body)
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        self.resume_ids.clear()
        with new_session() as session:
            resumes = session.exec(select(Resume).order_by(Resume.created_at.desc())).all()
            for resume in resumes:
                self.resume_ids.append(resume.id)
                self.list_widget.addItem(f"#{resume.id}  {resume.filename}")
        if self.resume_ids:
            self.list_widget.setCurrentRow(0)

    def import_resume(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar currículo",
            "",
            "Currículos (*.pdf *.docx *.txt)",
        )
        if not path:
            return
        try:
            raw_text = extract_text_from_file(path)
            if not raw_text:
                raise RuntimeError("Não foi possível extrair texto do arquivo.")
            source = Path(path)
            target = RESUMES_DIR / f"{source.stem}_{int(source.stat().st_mtime)}{source.suffix}"
            shutil.copy2(source, target)
            resume = Resume(
                filename=source.name,
                file_path=str(target),
                raw_text=raw_text,
                summary=summarize_resume(raw_text),
                skills_json=json.dumps(extract_basic_skills(raw_text), ensure_ascii=False),
            )
            with new_session() as session:
                session.add(resume)
                session.commit()
            self.refresh()
            if self.on_changed:
                self.on_changed()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao importar currículo", str(exc))

    def show_preview(self, row: int) -> None:
        if row < 0 or row >= len(self.resume_ids):
            self.preview.clear()
            return
        with new_session() as session:
            resume = session.get(Resume, self.resume_ids[row])
            if resume:
                skills = ", ".join(json.loads(resume.skills_json or "[]"))
                self.preview.setPlainText(
                    f"Resumo:\n{resume.summary}\n\nHabilidades detectadas:\n{skills}\n\nTexto extraído:\n{resume.raw_text}"
                )

    def set_primary(self) -> None:
        QMessageBox.information(
            self,
            "Currículo principal",
            "Neste MVP, o currículo mais recente é usado como principal nas análises.",
        )

    def enhance_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.resume_ids):
            QMessageBox.warning(self, "Selecione um currículo", "Escolha um currículo para estruturar com IA.")
            return
        with new_session() as session:
            resume = session.get(Resume, self.resume_ids[row])
            if not resume:
                QMessageBox.warning(self, "Currículo não encontrado", "Não foi possível carregar o currículo.")
                return
            resume_id = resume.id
            raw_text = resume.raw_text

        self.enhance_button.setEnabled(False)
        self.enhance_button.setText("Estruturando...")
        self.thread = QThread()
        self.worker = ResumeEnhanceWorker(resume_id, raw_text)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._enhance_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def _enhance_finished(self, resume_id: int, summary: str, skills: list, error: str) -> None:
        with new_session() as session:
            resume = session.get(Resume, resume_id)
            if resume:
                resume.summary = summary
                resume.skills_json = json.dumps(skills, ensure_ascii=False)
                session.add(resume)
                session.commit()

        self.enhance_button.setEnabled(True)
        self.enhance_button.setText("Estruturar com IA")
        self.refresh()
        if error:
            QMessageBox.warning(
                self,
                "IA indisponível",
                "Usei a extração local porque a IA não retornou um formato aproveitável. "
                "Tente novamente em alguns instantes.",
            )
        else:
            QMessageBox.information(self, "Currículo estruturado", "A IA organizou o currículo para análises e e-mails.")
        if self.on_changed:
            self.on_changed()
