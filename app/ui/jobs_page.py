import logging

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlmodel import select

from app.database import new_session
from app.models import Job, Resume
from app.services.job_analyzer import analyze_job
from app.services.job_hunter import (
    AUTO_RESULTS_PER_CYCLE,
    DEFAULT_PRIORITY_TOPICS,
    DEFAULT_SEARCH_PREFERENCES,
    clean_bad_fit_jobs,
    clean_low_quality_jobs,
    hunt_jobs_for_resume,
    reset_seen_urls,
)
from app.ui.dialogs import HuntJobsDialog, JobDialog


AUTO_HUNT_INTERVAL_MS = 10_000
FIRST_AUTO_HUNT_DELAY_MS = 1_000
logger = logging.getLogger(__name__)


class AnalysisWorker(QObject):
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, resume_id: int, job_id: int):
        super().__init__()
        self.resume_id = resume_id
        self.job_id = job_id

    def run(self) -> None:
        try:
            logger.info("Iniciando analise de vaga resume_id=%s job_id=%s", self.resume_id, self.job_id)
            with new_session() as session:
                analysis = analyze_job(session, self.resume_id, self.job_id)
            self.finished.emit(analysis.id)
        except Exception as exc:
            logger.exception("Erro no worker de analise")
            self.error.emit(str(exc))


class HuntJobsWorker(QObject):
    finished = Signal(int, int, str)
    error = Signal(str)

    def __init__(self, resume_id: int, preference: str, max_results: int, priority_topics: str):
        super().__init__()
        self.resume_id = resume_id
        self.preference = preference
        self.max_results = max_results
        self.priority_topics = priority_topics

    def run(self) -> None:
        try:
            logger.info(
                "Iniciando radar resume_id=%s max_results=%s topics=%s",
                self.resume_id,
                self.max_results,
                self.priority_topics,
            )
            with new_session() as session:
                saved, skipped, summary = hunt_jobs_for_resume(
                    session=session,
                    resume_id=self.resume_id,
                    location=self.preference,
                    max_results=self.max_results,
                    priority_topics=self.priority_topics,
                )
            logger.info("Radar finalizado: %s", summary)
            self.finished.emit(saved, skipped, summary)
        except Exception as exc:
            logger.exception("Erro no worker do radar")
            self.error.emit(str(exc))


class JobsPage(QWidget):
    def __init__(self, on_changed=None):
        super().__init__()
        self.on_changed = on_changed
        self.job_ids: list[int] = []
        self.analysis_thread: QThread | None = None
        self.analysis_worker: AnalysisWorker | None = None
        self.hunt_thread: QThread | None = None
        self.hunt_worker: HuntJobsWorker | None = None
        self.radar_paused = False
        self.last_preference = DEFAULT_SEARCH_PREFERENCES
        self.last_topics = DEFAULT_PRIORITY_TOPICS

        self.add_button = QPushButton("Cadastrar vaga")
        self.add_button.setObjectName("PrimaryButton")
        self.hunt_button = QPushButton("Acelerar radar")
        self.pause_button = QPushButton("Pausar radar")
        self.clean_button = QPushButton("Limpar resultados ruins")
        self.clean_bad_fit_button = QPushButton("Limpar vagas sem relação")
        self.demo_button = QPushButton("Importar vagas demo")
        self.analyze_button = QPushButton("Analisar com IA")
        self.status_label = QLabel("Radar de portais ativo: aguardando currículo.")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["todas", "email_auto", "sensitive_platform", "manual_review", "bad_fit"])
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Título", "Empresa", "Local", "Canal", "E-mail", "URL"])
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.add_button.clicked.connect(self.add_job)
        self.hunt_button.clicked.connect(self.hunt_jobs)
        self.pause_button.clicked.connect(self.toggle_radar)
        self.clean_button.clicked.connect(self.clean_bad_results)
        self.clean_bad_fit_button.clicked.connect(self.clean_bad_fit_results)
        self.demo_button.clicked.connect(self.import_demo)
        self.analyze_button.clicked.connect(self.analyze_selected)
        self.filter_combo.currentTextChanged.connect(self.refresh)

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(8)
        primary_actions.addWidget(self.add_button)
        primary_actions.addWidget(self.hunt_button)
        primary_actions.addWidget(self.pause_button)
        primary_actions.addWidget(self.analyze_button)
        primary_actions.addStretch()
        primary_actions.addWidget(QLabel("Filtro"))
        primary_actions.addWidget(self.filter_combo)

        maintenance_actions = QHBoxLayout()
        maintenance_actions.setSpacing(8)
        maintenance_actions.addWidget(self.clean_button)
        maintenance_actions.addWidget(self.clean_bad_fit_button)
        maintenance_actions.addWidget(self.demo_button)
        maintenance_actions.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addLayout(primary_actions)
        layout.addLayout(maintenance_actions)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table)
        self.refresh()

        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.setInterval(AUTO_HUNT_INTERVAL_MS)
        self.auto_timer.timeout.connect(self.run_auto_hunt)
        self.auto_timer.start(FIRST_AUTO_HUNT_DELAY_MS)

    def refresh(self) -> None:
        channel = self.filter_combo.currentText()
        self.table.setRowCount(0)
        self.job_ids.clear()
        with new_session() as session:
            statement = select(Job).order_by(Job.created_at.desc())
            if channel != "todas":
                statement = statement.where(Job.channel == channel)
            jobs = session.exec(statement).all()
            self.table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                self.job_ids.append(job.id)
                values = [job.title, job.company, job.location, job.channel, job.contact_email, job.url]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value or ""))

    def add_job(self) -> None:
        dialog = JobDialog(self)
        if dialog.exec() != JobDialog.Accepted:
            return
        data = dialog.values()
        if not data["title"] or not data["description"]:
            QMessageBox.warning(self, "Vaga incompleta", "Informe pelo menos título e descrição.")
            return
        with new_session() as session:
            session.add(Job(**data))
            session.commit()
        self.refresh()
        if self.on_changed:
            self.on_changed()

    def import_demo(self) -> None:
        demo_jobs = [
            Job(
                title="Desenvolvedor Python Júnior",
                company="Empresa Exemplo",
                location="Remoto",
                url="https://example.invalid/vagas/python-junior",
                source="Demo",
                contact_email="rh@example.invalid",
                description="Vaga para Python, SQL, Git e APIs. Perfil júnior com vontade de aprender.",
                channel="email_auto",
            ),
            Job(
                title="Pessoa Desenvolvedora Backend",
                company="LinkedIn Demo",
                location="São Paulo",
                url="https://www.linkedin.com/jobs/view/exemplo",
                source="LinkedIn",
                description="Backend Python, integração com APIs e banco de dados.",
                channel="sensitive_platform",
            ),
            Job(
                title="Analista de Sistemas",
                company="Gupy Demo",
                location="Híbrido",
                url="https://empresa.gupy.io/jobs/exemplo",
                source="Gupy",
                description="Análise de requisitos, SQL, documentação e contato com áreas de negócio.",
                channel="sensitive_platform",
            ),
            Job(
                title="Desenvolvedor de Automações",
                company="Site Empresa",
                location="Remoto",
                url="https://siteempresa.com/carreiras",
                source="Site institucional",
                description="Automação com Python, manipulação de arquivos, APIs e relatórios.",
                channel="manual_review",
            ),
        ]
        with new_session() as session:
            for job in demo_jobs:
                session.add(job)
            session.commit()
        self.refresh()
        if self.on_changed:
            self.on_changed()

    def run_auto_hunt(self) -> None:
        try:
            if self.radar_paused:
                self.status_label.setText("Radar pausado.")
                return
            self._start_radar_for_current_resume(self.last_preference, silent=True)
        except Exception as exc:
            logger.exception("Erro no ciclo automatico do radar")
            self.radar_paused = True
            self.pause_button.setText("Retomar radar")
            self.status_label.setText(f"Radar pausado por erro. Veja data/careerpilot.log. {exc}")

    def hunt_jobs(self) -> None:
        dialog = HuntJobsDialog(self)
        if dialog.exec() != HuntJobsDialog.Accepted:
            return
        values = dialog.values()
        self.last_preference = values["location"]
        self.last_topics = values["topics"]
        self._start_radar_for_current_resume(values["location"], silent=True)

    def _start_radar_for_current_resume(self, preference: str, silent: bool) -> None:
        try:
            with new_session() as session:
                resume = session.exec(select(Resume).order_by(Resume.created_at.desc())).first()
                if not resume:
                    self.status_label.setText("Radar de portais ativo: importe um currículo para iniciar buscas.")
                    if not silent:
                        QMessageBox.warning(self, "Sem currículo", "Importe e estruture um currículo antes de buscar vagas.")
                    return
                resume_id = resume.id
            self.start_hunt(resume_id, preference, AUTO_RESULTS_PER_CYCLE, silent=silent)
        except Exception:
            logger.exception("Erro ao iniciar radar para curriculo atual")
            raise

    def toggle_radar(self) -> None:
        self.radar_paused = not self.radar_paused
        self.pause_button.setText("Retomar radar" if self.radar_paused else "Pausar radar")
        self.status_label.setText("Radar pausado." if self.radar_paused else "Radar de portais ativo.")
        if not self.radar_paused:
            self.run_auto_hunt()

    def start_hunt(self, resume_id: int, preference: str, max_results: int, silent: bool) -> None:
        if self._hunt_is_running():
            self.status_label.setText("Radar de portais: busca em andamento.")
            self._schedule_next_auto_hunt()
            return

        self.auto_timer.stop()
        self.hunt_button.setEnabled(False)
        self.hunt_button.setText("Radar ativo...")
        self.status_label.setText(
            "Radar de portais: vasculhando LinkedIn, InfoJobs, Gupy, Indeed, Vagas.com, Catho, Glassdoor, Remotar, Programathor e Trampos..."
        )
        self.hunt_thread = QThread()
        self.hunt_worker = HuntJobsWorker(resume_id, preference, max_results, self.last_topics)
        self.hunt_worker.moveToThread(self.hunt_thread)
        self.hunt_thread.started.connect(self.hunt_worker.run)
        self.hunt_worker.finished.connect(self._hunt_finished)
        self.hunt_worker.error.connect(self._hunt_error)
        self.hunt_worker.finished.connect(self.hunt_thread.quit)
        self.hunt_worker.error.connect(self.hunt_thread.quit)
        self.hunt_thread.finished.connect(self.hunt_worker.deleteLater)
        self.hunt_thread.finished.connect(self.hunt_thread.deleteLater)
        self.hunt_thread.finished.connect(self._cleanup_hunt_thread)
        self.hunt_thread.start()

    def _hunt_is_running(self) -> bool:
        if not self.hunt_thread:
            return False
        try:
            return self.hunt_thread.isRunning()
        except RuntimeError:
            self.hunt_thread = None
            self.hunt_worker = None
            return False

    def _cleanup_hunt_thread(self) -> None:
        self.hunt_thread = None
        self.hunt_worker = None

    def _hunt_finished(self, saved: int, skipped: int, summary: str) -> None:
        try:
            self.hunt_button.setEnabled(True)
            self.hunt_button.setText("Acelerar radar")
            self.refresh()
            self.status_label.setText(f"Radar de portais: {summary} Próximo ciclo em instantes.")
            if self.on_changed:
                self.on_changed()
            self._schedule_next_auto_hunt()
        except Exception as exc:
            logger.exception("Erro ao finalizar radar na interface")
            self.radar_paused = True
            self.pause_button.setText("Retomar radar")
            self.status_label.setText(f"Radar pausado por erro na interface. Veja data/careerpilot.log. {exc}")

    def _hunt_error(self, message: str) -> None:
        logger.error("Radar retornou erro: %s", message)
        self.hunt_button.setEnabled(True)
        self.hunt_button.setText("Acelerar radar")
        self.radar_paused = True
        self.pause_button.setText("Retomar radar")
        self.status_label.setText(f"Radar pausado por erro na ultima busca. Veja data/careerpilot.log. {message}")

    def _schedule_next_auto_hunt(self) -> None:
        if self.radar_paused:
            return
        if not self.auto_timer.isActive():
            self.auto_timer.start(AUTO_HUNT_INTERVAL_MS)

    def closeEvent(self, event) -> None:
        logger.info("Fechando JobsPage")
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self.auto_timer.stop()
        for thread in (self.hunt_thread, self.analysis_thread):
            if thread and thread.isRunning():
                thread.quit()
                thread.wait(3000)

    def clean_bad_results(self) -> None:
        with new_session() as session:
            deleted = clean_low_quality_jobs(session)
        reset_seen_urls()
        self.refresh()
        self.status_label.setText(f"Limpeza concluída: {deleted} resultados ruins removidos; histórico de URLs resetado.")
        if self.on_changed:
            self.on_changed()

    def clean_bad_fit_results(self) -> None:
        with new_session() as session:
            deleted = clean_bad_fit_jobs(session)
        self.refresh()
        self.status_label.setText(f"Limpeza concluída: {deleted} vagas sem relação removidas.")
        if self.on_changed:
            self.on_changed()

    def _selected_job_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.job_ids):
            return None
        return self.job_ids[row]

    def analyze_selected(self) -> None:
        job_id = self._selected_job_id()
        if not job_id:
            QMessageBox.warning(self, "Selecione uma vaga", "Escolha uma vaga para analisar.")
            return
        with new_session() as session:
            resume = session.exec(select(Resume).order_by(Resume.created_at.desc())).first()
            if not resume:
                QMessageBox.warning(self, "Sem currículo", "Importe um currículo antes de analisar vagas.")
                return
            resume_id = resume.id

        self.analyze_button.setEnabled(False)
        self.analyze_button.setText("Analisando...")
        self.analysis_thread = QThread()
        self.analysis_worker = AnalysisWorker(resume_id, job_id)
        self.analysis_worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.analysis_worker.run)
        self.analysis_worker.finished.connect(self._analysis_finished)
        self.analysis_worker.error.connect(self._analysis_error)
        self.analysis_worker.finished.connect(self.analysis_thread.quit)
        self.analysis_worker.error.connect(self.analysis_thread.quit)
        self.analysis_thread.finished.connect(self.analysis_worker.deleteLater)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        self.analysis_thread.finished.connect(self._cleanup_analysis_thread)
        self.analysis_thread.start()

    def _cleanup_analysis_thread(self) -> None:
        self.analysis_thread = None
        self.analysis_worker = None

    def _analysis_finished(self, analysis_id: int) -> None:
        self.analyze_button.setEnabled(True)
        self.analyze_button.setText("Analisar com IA")
        QMessageBox.information(self, "Análise concluída", f"Análise #{analysis_id} salva no banco.")
        if self.on_changed:
            self.on_changed()

    def _analysis_error(self, message: str) -> None:
        self.analyze_button.setEnabled(True)
        self.analyze_button.setText("Analisar com IA")
        QMessageBox.critical(self, "Erro na análise", message)
