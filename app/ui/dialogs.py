from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from app.services.channel_classifier import classify_channel
from app.services.job_hunter import AUTO_RESULTS_PER_CYCLE, DEFAULT_PRIORITY_TOPICS, DEFAULT_SEARCH_PREFERENCES


class JobDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cadastrar vaga")
        self.setMinimumWidth(620)

        self.title_input = QLineEdit()
        self.company_input = QLineEdit()
        self.location_input = QLineEdit()
        self.url_input = QLineEdit()
        self.source_input = QLineEdit()
        self.email_input = QLineEdit()
        self.description_input = QTextEdit()
        self.description_input.setMinimumHeight(220)

        form = QFormLayout()
        form.addRow("Título", self.title_input)
        form.addRow("Empresa", self.company_input)
        form.addRow("Localização", self.location_input)
        form.addRow("URL", self.url_input)
        form.addRow("Fonte", self.source_input)
        form.addRow("E-mail direto", self.email_input)
        form.addRow("Descrição", self.description_input)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def values(self) -> dict:
        url = self.url_input.text().strip()
        email = self.email_input.text().strip()
        return {
            "title": self.title_input.text().strip(),
            "company": self.company_input.text().strip(),
            "location": self.location_input.text().strip(),
            "url": url,
            "source": self.source_input.text().strip(),
            "contact_email": email,
            "description": self.description_input.toPlainText().strip(),
            "channel": classify_channel(url, email),
        }


class AnalysisDetailsDialog(QDialog):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(720, 560)

        label = QLabel(title)
        label.setObjectName("HeaderTitle")
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(content)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(text)
        layout.addWidget(buttons)


class HuntJobsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Radar de vagas")
        self.setMinimumWidth(620)

        self.location_input = QLineEdit(DEFAULT_SEARCH_PREFERENCES)
        self.topics_input = QLineEdit(DEFAULT_PRIORITY_TOPICS)

        info = QLabel(
            "O radar roda em ciclos curtos e contínuos enquanto o app estiver aberto e prioriza portais de emprego. "
            "A IA interpreta o currículo e salva apenas vagas com evidência de compatibilidade por cargo, habilidades, nível e modalidade. "
            "Fontes preferenciais: LinkedIn, InfoJobs, Gupy, Indeed, Vagas.com, Catho, Glassdoor, Remotar, Programathor e Trampos."
        )
        info.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Preferência", self.location_input)
        form.addRow("Tópicos prioritários", self.topics_input)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def values(self) -> dict:
        return {
            "location": self.location_input.text().strip() or DEFAULT_SEARCH_PREFERENCES,
            "topics": self.topics_input.text().strip() or DEFAULT_PRIORITY_TOPICS,
            "max_results": AUTO_RESULTS_PER_CYCLE,
        }
