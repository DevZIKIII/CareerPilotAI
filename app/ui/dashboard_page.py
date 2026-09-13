from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from sqlmodel import func, select

from app.config import openrouter_status, smtp_status
from app.database import new_session
from app.models import Analysis, Application, Job


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "0"):
        super().__init__()
        self.setObjectName("Card")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("CardValue")
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.cards = {
            "jobs": MetricCard("Total de vagas"),
            "analyses": MetricCard("Vagas analisadas"),
            "avg": MetricCard("Match médio"),
            "sent": MetricCard("Envios automáticos"),
            "sensitive": MetricCard("Plataformas sensíveis"),
            "manual": MetricCard("Aguardando revisão"),
        }
        self.openrouter_label = QLabel()
        self.smtp_label = QLabel()
        self.latest_table = QTableWidget(0, 4)
        self.latest_table.setHorizontalHeaderLabels(["Vaga", "Empresa", "Score", "Recomendação"])
        self.latest_table.horizontalHeader().setStretchLastSection(True)

        grid = QGridLayout()
        for index, card in enumerate(self.cards.values()):
            grid.addWidget(card, index // 3, index % 3)

        layout = QVBoxLayout(self)
        title = QLabel("Dashboard")
        title.setObjectName("HeaderTitle")
        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addWidget(QLabel("Status da configuração"))
        layout.addWidget(self.openrouter_label)
        layout.addWidget(self.smtp_label)
        layout.addWidget(QLabel("Últimas vagas analisadas"))
        layout.addWidget(self.latest_table)
        self.refresh()

    def refresh(self) -> None:
        with new_session() as session:
            total_jobs = session.exec(select(func.count(Job.id))).one()
            total_analyses = session.exec(select(func.count(Analysis.id))).one()
            avg_score = session.exec(select(func.avg(Analysis.score))).one()
            sent = session.exec(select(func.count(Application.id)).where(Application.status == "sent")).one()
            sensitive = session.exec(select(func.count(Job.id)).where(Job.channel == "sensitive_platform")).one()
            manual = session.exec(select(func.count(Job.id)).where(Job.channel == "manual_review")).one()

            self.cards["jobs"].set_value(str(total_jobs or 0))
            self.cards["analyses"].set_value(str(total_analyses or 0))
            self.cards["avg"].set_value(f"{int(avg_score or 0)}%")
            self.cards["sent"].set_value(str(sent or 0))
            self.cards["sensitive"].set_value(str(sensitive or 0))
            self.cards["manual"].set_value(str(manual or 0))

            self.openrouter_label.setText(f"OpenRouter: {openrouter_status()}")
            self.smtp_label.setText(f"SMTP: {smtp_status()}")

            rows = session.exec(select(Analysis, Job).join(Job).order_by(Analysis.created_at.desc()).limit(8)).all()
            self.latest_table.setRowCount(len(rows))
            for row, (analysis, job) in enumerate(rows):
                values = [job.title, job.company, str(analysis.score), analysis.recommendation[:120]]
                for col, value in enumerate(values):
                    self.latest_table.setItem(row, col, QTableWidgetItem(value or ""))
