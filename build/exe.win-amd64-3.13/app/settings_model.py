from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class PotentialFiltersSettings:
    exclude_no_phone: bool = True
    exclude_blue_checkmark: bool = True
    exclude_green_checkmark: bool = True
    exclude_good_place: bool = True
    exclude_noncommercial: bool = True
    max_rating: Optional[float] = None
    stop_words: str = ""
    white_list: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "PotentialFiltersSettings":
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        require_checkmark = data.get("require_checkmark", None)
        max_rating = data.get("max_rating", defaults.max_rating)
        if max_rating not in (None, ""):
            try:
                max_rating = float(str(max_rating).replace(",", "."))
            except Exception:
                max_rating = defaults.max_rating
        if "exclude_blue_checkmark" in data or "exclude_green_checkmark" in data:
            exclude_blue_checkmark = bool(
                data.get("exclude_blue_checkmark", defaults.exclude_blue_checkmark)
            )
            exclude_green_checkmark = bool(
                data.get("exclude_green_checkmark", defaults.exclude_green_checkmark)
            )
        elif require_checkmark is not None:
            exclude_blue_checkmark = bool(require_checkmark)
            exclude_green_checkmark = bool(require_checkmark)
        else:
            exclude_blue_checkmark = defaults.exclude_blue_checkmark
            exclude_green_checkmark = defaults.exclude_green_checkmark
        return cls(
            exclude_no_phone=bool(data.get("exclude_no_phone", defaults.exclude_no_phone)),
            exclude_blue_checkmark=exclude_blue_checkmark,
            exclude_green_checkmark=exclude_green_checkmark,
            exclude_good_place=bool(data.get("exclude_good_place", defaults.exclude_good_place)),
            exclude_noncommercial=bool(data.get("exclude_noncommercial", defaults.exclude_noncommercial)),
            max_rating=max_rating,
            stop_words=str(data.get("stop_words", defaults.stop_words) or ""),
            white_list=str(data.get("white_list", defaults.white_list) or ""),
        )


@dataclass
class ProgramSettings:
    headless: bool = False
    block_images: bool = True
    block_media: bool = True
    open_result: bool = True
    log_level: str = "info"
    autosave_settings: bool = True

    @classmethod
    def from_dict(cls, data: Any) -> "ProgramSettings":
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            headless=bool(data.get("headless", defaults.headless)),
            block_images=bool(data.get("block_images", defaults.block_images)),
            block_media=bool(data.get("block_media", defaults.block_media)),
            open_result=bool(data.get("open_result", defaults.open_result)),
            log_level=str(data.get("log_level", defaults.log_level) or defaults.log_level),
            autosave_settings=bool(data.get("autosave_settings", defaults.autosave_settings)),
        )


@dataclass
class NotificationsSettings:
    on_finish: bool = True
    on_captcha: bool = True
    on_error: bool = True
    on_autosave: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "NotificationsSettings":
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            on_finish=bool(data.get("on_finish", defaults.on_finish)),
            on_captcha=bool(data.get("on_captcha", defaults.on_captcha)),
            on_error=bool(data.get("on_error", defaults.on_error)),
            on_autosave=bool(data.get("on_autosave", defaults.on_autosave)),
        )


@dataclass
class Settings:
    potential_filters: PotentialFiltersSettings = field(default_factory=PotentialFiltersSettings)
    program: ProgramSettings = field(default_factory=ProgramSettings)
    notifications: NotificationsSettings = field(default_factory=NotificationsSettings)

    @classmethod
    def from_dict(cls, data: Any) -> "Settings":
        if not isinstance(data, dict):
            return cls()
        return cls(
            potential_filters=PotentialFiltersSettings.from_dict(data.get("potential_filters", {})),
            program=ProgramSettings.from_dict(data.get("program", {})),
            notifications=NotificationsSettings.from_dict(data.get("notifications", {})),
        )

    def to_dict(self) -> dict:
        return asdict(self)
