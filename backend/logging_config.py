import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

HTTP_LOG_FILE = Path(__file__).parent / "logs" / "http.log"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a readable console format for backend observability."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-40s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Avoid duplicate handlers on reload
    root.handlers = [handler]

    # Quiet down noisy third-party loggers
    for noisy in ("httpcore", "httpx", "urllib3", "chromadb", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # File handler for HTTP request/response bodies (separate from console)
    HTTP_LOG_FILE.parent.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(HTTP_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    http_logger = logging.getLogger("http")
    http_logger.setLevel(logging.DEBUG)
    # Avoid duplicate handlers on reload
    http_logger.handlers = [file_handler]
    http_logger.propagate = False
