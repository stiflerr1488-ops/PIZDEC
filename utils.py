from __future__ import annotations

import random
import re
import time
from typing import Optional


RATING_RE = re.compile(r"\d+[\.,]\d+")
COUNT_RE = re.compile(r"\d+")
PHONE_RE = re.compile(r"(?:\+?7|8)\s*\(?\d{3}\)?[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")


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
