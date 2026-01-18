from __future__ import annotations

import re

from app.settings_model import Settings


NONCOMMERCIAL_KEYWORDS = [
    "школа",
    "детский сад",
    "садик",
    "университет",
    "колледж",
    "техникум",
    "больница",
    "поликлиника",
    "мфц",
    "администрация",
    "муницип",
    "гос",
    "государ",
    "библиотека",
    "музей",
    "загс",
    "налоговая",
    "паспортный",
    "соц",
    "центр занятости",
]

PRIVATE_EXCEPTION_KEYWORDS = [
    "детский сад",
    "ясли",
    "школа",
    "лицей",
    "гимназия",
    "колледж",
    "техникум",
    "институт",
    "университет",
    "академия",
    "училище",
    "пту",
    "дополнительное образование",
    "музыкальная школа",
    "художественная школа",
]

SCHOOL_ABBREVIATION_PATTERN = re.compile(r"\b(?:сош|гсош|мсош)\s*\d")
EDU_OWNER_KEYWORDS = ("мбоу", "маоу", "мкоу", "гбоу")
EDU_TYPE_KEYWORDS = ("сош", "доу", "лицей", "гимназия")


def _parse_list(value: str) -> list[str]:
    if not value:
        return []
    items = []
    for part in value.split(","):
        cleaned = part.strip().lower()
        if cleaned:
            items.append(cleaned)
    return items


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    normalized = value.lower().replace("ё", "е")
    normalized = re.sub(r"[.\-/\\\"'“”«»]", " ", normalized)
    normalized = re.sub(r"[№]", " ", normalized)
    normalized = re.sub(r"\b(?:no|n)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _get_attr(row, name: str, default: str = "") -> str:
    if isinstance(row, dict):
        return str(row.get(name, default) or "")
    return str(getattr(row, name, default) or "")


def _get_rating(row) -> float | None:
    if isinstance(row, dict):
        value = row.get("rating")
    else:
        value = getattr(row, "rating", None)
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def is_noncommercial(row) -> bool:
    name = _normalize_text(_get_attr(row, "name"))
    if not name:
        return False
    return any(keyword in name for keyword in NONCOMMERCIAL_KEYWORDS)


def is_private_exception(name: str) -> bool:
    if "частн" not in name:
        return False
    return any(keyword in name for keyword in PRIVATE_EXCEPTION_KEYWORDS)


def has_school_abbreviation(name: str) -> bool:
    if SCHOOL_ABBREVIATION_PATTERN.search(name):
        return True
    if any(owner in name for owner in EDU_OWNER_KEYWORDS) and any(
        keyword in name for keyword in EDU_TYPE_KEYWORDS
    ):
        return True
    return False


def passes_potential_filters(row, settings: Settings) -> bool:
    filters = settings.potential_filters
    raw_name = _get_attr(row, "name")
    name = _normalize_text(raw_name)
    phone = _get_attr(row, "phone") or _get_attr(row, "phones")
    check_mark = (_get_attr(row, "check_mark") or _get_attr(row, "verified")).lower()
    good_place = _get_attr(row, "good_place") or _get_attr(row, "award")
    rating = _get_rating(row)
    private_exception = is_private_exception(name)

    white_list = _parse_list(filters.white_list)
    if white_list:
        if not any(word in name for word in white_list):
            return False

    stop_words = [_normalize_text(word) for word in _parse_list(filters.stop_words)]
    if stop_words and (
        any(word in name for word in stop_words) or has_school_abbreviation(name)
    ) and not private_exception:
        return False

    if filters.exclude_no_phone and not phone.strip():
        return False

    if filters.require_checkmark and check_mark not in {"синяя", "зелёная", "зеленая"}:
        return False

    if filters.exclude_good_place and good_place.strip():
        return False

    if filters.max_rating is not None and rating is not None:
        if rating > float(filters.max_rating):
            return False

    if filters.exclude_noncommercial and is_noncommercial(row) and not private_exception:
        return False

    return True
