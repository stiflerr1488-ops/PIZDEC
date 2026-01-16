from __future__ import annotations

import random
import re
import time
from typing import Optional


RATING_RE = re.compile(r"\d+[\.,]\d+")
COUNT_RE = re.compile(r"\d+")


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
