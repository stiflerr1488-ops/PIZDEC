from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from playwright.sync_api import sync_playwright

from excel_writer import ExcelWriter
from parser_search import build_serp_url, parse_serp_cards
from utils import RateLimiter
from yandex_maps_scraper import Organization


def _rows_to_organizations(rows: Iterable[dict]) -> list[Organization]:
    organizations: list[Organization] = []
    for row in rows:
        badge = "синяя" if row.get("badge_blue") else ""
        org = Organization(
            name=row.get("name", ""),
            phone=row.get("phones", ""),
            verified=badge,
            award=row.get("good_place", ""),
            vk=row.get("vk", ""),
            telegram=row.get("telegram", ""),
            whatsapp="",
            website="",
            card_url=row.get("url", ""),
            rating=row.get("rating", ""),
            rating_count=row.get("reviews", ""),
        )
        organizations.append(org)
    return organizations


def run_fast_parser(
    *,
    query: str,
    output_path: Path,
    lr: str,
    max_clicks: int,
    delay_min_s: float,
    delay_max_s: float,
    stop_event,
    pause_event,
    captcha_resume_event,
    log: Callable[[str], None],
    progress: Optional[Callable[[dict], None]] = None,
) -> int:
    url = build_serp_url(query, lr)
    log(f"Быстрый режим: открываю поиск → {url}")
    rate_limiter = RateLimiter(min_delay_s=delay_min_s, max_delay_s=delay_max_s)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        page.set_default_timeout(20000)
        page.goto(url, wait_until="domcontentloaded")

        rows = parse_serp_cards(
            page,
            max_clicks=max_clicks,
            arrow_delay_ms=25,
            card_delay_ms=10,
            phone_delay_ms=12,
            stop_event=stop_event,
            pause_event=pause_event,
            log=log,
            captcha_resume_event=captcha_resume_event,
            progress=progress,
            delay_min_s=delay_min_s,
            delay_max_s=delay_max_s,
            rate_limiter=rate_limiter,
        )

        organizations = _rows_to_organizations(rows)
        writer = ExcelWriter(output_path)
        try:
            for org in organizations:
                if stop_event.is_set():
                    break
                writer.append(org)
        finally:
            writer.close()
            context.close()
            browser.close()
    return len(organizations)
