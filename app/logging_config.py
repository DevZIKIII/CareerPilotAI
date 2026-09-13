import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import sys
import threading

from app.config import DATA_DIR


LOG_PATH = DATA_DIR / "careerpilot.log"
CRASH_PATH = DATA_DIR / "careerpilot_crash.log"
_crash_file = None


def setup_logging() -> None:
    global _crash_file
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
        force=True,
    )

    if _crash_file is None or _crash_file.closed:
        _crash_file = CRASH_PATH.open("a", encoding="utf-8")
    faulthandler.enable(file=_crash_file, all_threads=True)

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("careerpilot").exception(
            "Excecao nao capturada",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    def handle_thread_exception(args: threading.ExceptHookArgs):
        logging.getLogger("careerpilot").exception(
            "Excecao nao capturada em thread",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
