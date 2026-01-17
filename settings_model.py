from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json

@dataclass
class Settings:
    lr: str = "120590"
    radius_z: str = "13"

    # serp | maps
    parse_mode: str = "serp"
    only_scan: bool = False
    only_parse: bool = False

    # ui
    speed_preset: str = "stable"  # stable|fast

    # browser
    headless: bool = True
    stealth_enabled: bool = True
    fingerprint_enabled: bool = True
    session_pool_enabled: bool = True
    browser_user_agent: str = ""  # optional UA override
    block_images: bool = True
    block_media: bool = True

    # ui behavior
    always_on_top: bool = False

    # notifications
    notify_on_complete: bool = True
    notify_on_captcha: bool = True
    notify_on_error: bool = True
    notify_on_autosave: bool = False

    # delays (ms) - base delays inside parsers
    arrow_delay_ms: int = 25
    card_delay_ms: int = 10
    phone_delay_ms: int = 12

    # anti-ban randomized delay between actions (seconds)
    delay_min_s: float = 0.0
    delay_max_s: float = 0.0

    # rate limiter / backoff
    backoff_base_s: float = 2.0
    backoff_max_s: float = 60.0
    batch_every_n: int = 0
    batch_pause_s: float = 2.0

    # parallelism (reserved; currently used for MAPS parse)
    parallelism: int = 1

    # limits
    max_clicks: int = 800
    max_links: int = 0

    # reliability
    retries_on_error: int = 2
    retry_pause_s: float = 2.0
    autosave_every_n: int = 120  # 0=off

    # soft start delay after browser launch (seconds)
    soft_start_min_s: float = 2.0
    soft_start_max_s: float = 7.0

    # filters
    stop_words: str = ""
    white_words: str = ""
    max_rating: float = 0.0
    exclude_noncommercial: bool = True
    require_phone: bool = True
    require_good_place: bool = False
    require_badge: bool = True
    exclude_good_place: bool = True

    # output
    output_format: str = "xlsx"  # xlsx|csv
    auto_open_excel: bool = True

    # logs
    log_level: str = "info"  # trace|info|warn

    # settings behavior
    auto_save_settings: bool = True

def _path(project_dir: Path) -> Path:
    return project_dir / "settings.json"

def load_settings(project_dir: Path) -> Settings:
    p = _path(project_dir)
    if not p.exists():
        return Settings()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        s = Settings()
        if isinstance(d, dict):
            for k, v in d.items():
                if hasattr(s, k):
                    setattr(s, k, v)
        return s
    except Exception:
        return Settings()

def save_settings(project_dir: Path, s: Settings) -> None:
    (_path(project_dir)).write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
