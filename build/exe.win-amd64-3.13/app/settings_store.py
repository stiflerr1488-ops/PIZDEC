from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .settings_model import Settings


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_settings() -> Settings:
    if not SETTINGS_PATH.exists():
        settings = Settings()
        save_settings(settings)
        return settings
    data = _read_json(SETTINGS_PATH)
    if data is None:
        return Settings()
    return Settings.from_dict(data)


def save_settings(settings: Settings) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = settings.to_dict()
    tmp_path = SETTINGS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, SETTINGS_PATH)
