from __future__ import annotations

import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


RATING_RE = re.compile(r"\d+[\.,]\d+")
COUNT_RE = re.compile(r"\d+")
PHONE_RE = re.compile(r"(?:\+?7|8)\D*\d(?:\D*\d){9}")

_LOGGER_NAME = "parser_serm"
_logger = logging.getLogger(_LOGGER_NAME)


def setup_logger(log_path: Path) -> None:
    if _logger.handlers:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)

    _logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S")

    file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)

    _logger.addHandler(file_handler)
    _logger.addHandler(stream_handler)


def configure_logging(
    level: str,
    log_path: Optional[Path] = None,
    full_log_path: Optional[Path] = None,
) -> None:
    level_name = (level or "info").upper()
    resolved_level = getattr(logging, level_name, logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(resolved_level)
    stream_handler.setFormatter(fmt)
    handlers.append(stream_handler)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8", mode="w")
        file_handler.setLevel(resolved_level)
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)

    if full_log_path is not None:
        full_log_path.parent.mkdir(parents=True, exist_ok=True)
        full_handler = logging.FileHandler(full_log_path, encoding="utf-8", mode="w")
        full_handler.setLevel(logging.DEBUG)
        full_handler.setFormatter(fmt)
        handlers.append(full_handler)

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers,
        force=True,
    )
    _logger.setLevel(logging.DEBUG)


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


def normalize_rating(text: str) -> str:
    if not text:
        return ""
    match = RATING_RE.search(text)
    if not match:
        return ""
    return match.group(0).replace(",", ".")


def extract_count(text: str) -> str:
    if not text:
        return ""
    match = COUNT_RE.search(text)
    return match.group(0) if match else ""


def human_delay(min_s: float = 0.3, max_s: float = 1.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def sanitize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def extract_phones(text: str) -> list[str]:
    if not text:
        return []
    phones: list[str] = []
    for match in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
        elif len(digits) == 10:
            digits = "7" + digits
        if len(digits) != 11:
            continue
        formatted = f"+{digits}"
        if formatted not in phones:
            phones.append(formatted)
    return phones


def split_query(query: str) -> tuple[str, str]:
    cleaned = (query or "").strip()
    if " в " in cleaned:
        niche, city = cleaned.split(" в ", 1)
        return niche.strip(), city.strip()
    return cleaned, ""


def _sanitize_filename(value: str, *, replace_colon: bool) -> str:
    sanitized = (value or "").strip().replace(" ", "_")
    forbidden = r'[<>"/\\|?*\n\r\t]'
    if replace_colon:
        forbidden = r'[<>:"/\\|?*\n\r\t]'
    sanitized = re.sub(forbidden, "-", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = re.sub(r"-+", "-", sanitized)
    return sanitized.strip("._-")


def build_result_paths(
    *,
    niche: str,
    city: str,
    results_dir: Path,
    now: datetime | None = None,
) -> tuple[Path, Path, Path]:
    timestamp = now or datetime.now()
    date_part = timestamp.strftime("%d.%m")
    time_part = timestamp.strftime("%H:%M")
    parts = [part for part in [niche.strip(), city.strip(), date_part, time_part] if part]
    base_name = "_".join(parts) if parts else f"{date_part}_{time_part}"
    replace_colon = os.name == "nt"
    safe_base = _sanitize_filename(base_name, replace_colon=replace_colon)
    safe_niche = _sanitize_filename(niche.strip() or "без_ниши", replace_colon=replace_colon)
    folder = results_dir / (safe_niche or "без_ниши")
    full_path = folder / f"{safe_base}_full.xlsx"
    potential_path = folder / f"{safe_base}_potential.xlsx"
    return full_path, potential_path, folder


def _wait_with_pause(stop_event, pause_event, total_s: float) -> None:
    end_time = time.time() + max(0.0, total_s)
    while time.time() < end_time and not stop_event.is_set():
        if pause_event is not None:
            while pause_event.is_set() and not stop_event.is_set():
                time.sleep(0.1)
        time.sleep(0.05)


def maybe_human_delay(stop_event, pause_event, min_s: float, max_s: float) -> None:
    delay = 0.0
    if max_s > 0:
        delay = random.uniform(max(0.0, min_s), max(0.0, max_s))
    elif min_s > 0:
        delay = max(0.0, min_s)
    if delay <= 0:
        return
    _wait_with_pause(stop_event, pause_event, delay)


class RateLimiter:
    def __init__(
        self,
        *,
        min_delay_s: float = 0.0,
        max_delay_s: float = 0.0,
        backoff_base_s: float = 2.0,
        backoff_max_s: float = 60.0,
    ) -> None:
        self.min_delay_s = min_delay_s
        self.max_delay_s = max_delay_s
        self.backoff_base_s = backoff_base_s
        self.backoff_max_s = backoff_max_s
        self._backoff_s = backoff_base_s

    def wait_action(self, stop_event, pause_event) -> None:
        delay = 0.0
        if self.max_delay_s > 0:
            delay = random.uniform(max(0.0, self.min_delay_s), max(0.0, self.max_delay_s))
        elif self.min_delay_s > 0:
            delay = max(0.0, self.min_delay_s)
        if delay > 0:
            _wait_with_pause(stop_event, pause_event, delay)

    def wait_backoff(self, stop_event, pause_event) -> None:
        delay = max(0.0, self._backoff_s)
        if delay > 0:
            _wait_with_pause(stop_event, pause_event, delay)
        self._backoff_s = min(self.backoff_max_s, max(self.backoff_base_s, self._backoff_s * 2))

    def maybe_batch_pause(
        self,
        index: int,
        batch_every_n: int,
        batch_pause_s: float,
        stop_event,
        pause_event,
    ) -> None:
        if batch_every_n <= 0:
            return
        if index % batch_every_n == 0:
            _wait_with_pause(stop_event, pause_event, max(0.0, batch_pause_s))

    def reset_backoff(self) -> None:
        self._backoff_s = self.backoff_base_s
