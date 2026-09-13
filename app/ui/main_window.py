import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.ui.analyses_page import AnalysesPage
from app.ui.applications_page import ApplicationsPage
from app.ui.dashboard_page import DashboardPage
from app.ui.jobs_page import JobsPage
from app.ui.resumes_page import ResumesPage


logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CareerPilot AI")
        self.setMinimumSize(1040, 680)
        self.resize(1180, 760)
        self.nav_buttons: list[QPushButton] = []

        self.stack = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.resumes_page = ResumesPage(self.refresh_all)
        self.jobs_page = JobsPage(self.refresh_all)
        self.analyses_page = AnalysesPage(self.refresh_all)
        self.applications_page = ApplicationsPage(self.refresh_all)

        for page in (
            self.dashboard_page,
            self.resumes_page,
            self.jobs_page,
            self.analyses_page,
            self.applications_page,
        ):
            self.stack.addWidget(page)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        title = QLabel("CareerPilot AI")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Desktop Windows")
        subtitle.setObjectName("Muted")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        for index, text in enumerate(["Dashboard", "Currículos", "Vagas", "Análises", "Candidaturas"]):
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.set_page(i))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()
        footer = QLabel("Sem automação em plataformas sensíveis")
        footer.setWordWrap(True)
        footer.setObjectName("Muted")
        layout.addWidget(footer)
        self.nav_buttons[0].setChecked(True)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        header = QLabel("Painel de carreira")
        header.setObjectName("HeaderTitle")
        layout.addWidget(header)
        layout.addWidget(self.stack, 1)
        return content

    def set_page(self, index: int) -> None:
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        self.stack.setCurrentIndex(index)
        current = self.stack.currentWidget()
        if hasattr(current, "refresh"):
            current.refresh()

    def refresh_all(self) -> None:
        for page in (
            self.dashboard_page,
            self.resumes_page,
            self.jobs_page,
            self.analyses_page,
            self.applications_page,
        ):
            if hasattr(page, "refresh"):
                page.refresh()

    def closeEvent(self, event) -> None:
        logger.info("Fechando MainWindow")
        if hasattr(self.jobs_page, "shutdown"):
            self.jobs_page.shutdown()
        super().closeEvent(event)
