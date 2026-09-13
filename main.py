import sys
import logging

from PySide6.QtWidgets import QApplication

from app.config import ensure_app_dirs
from app.database import init_db
from app.logging_config import setup_logging
from app.ui.main_window import MainWindow
from app.ui.styles import APP_QSS


def main() -> int:
    ensure_app_dirs()
    setup_logging()
    logging.getLogger("careerpilot").info("Iniciando CareerPilot AI")
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("CareerPilot AI")
    app.setStyleSheet(APP_QSS)
    app.aboutToQuit.connect(lambda: logging.getLogger("careerpilot").info("Aplicativo encerrando"))

    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
