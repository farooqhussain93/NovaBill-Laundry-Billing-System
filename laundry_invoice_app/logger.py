from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOGS_DIR

_LOGGER_NAME = "novabill"


def get_logger() -> logging.Logger:
    """Return the application logger, configured once with rotating file output."""
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        LOGS_DIR / "app.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
