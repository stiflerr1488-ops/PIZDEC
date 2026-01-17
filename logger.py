from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "parser_serm"
_logger = logging.getLogger(_LOGGER_NAME)


def setup_logger(log_path: Path) -> None:
    if _logger.handlers:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)

    _logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)

    _logger.addHandler(file_handler)
    _logger.addHandler(stream_handler)


def log(msg: str, level: str = "info") -> None:
    level = (level or "info").lower()
    if level == "warn":
        _logger.warning(msg)
    elif level == "error":
        _logger.error(msg)
    elif level == "debug":
        _logger.debug(msg)
    else:
        _logger.info(msg)


def log_exception(msg: str, exc: Optional[BaseException] = None) -> None:
    if exc is not None:
        _logger.error(msg, exc_info=exc)
    else:
        _logger.error(msg, exc_info=True)


def get_logger() -> logging.Logger:
    return _logger
