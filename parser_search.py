from __future__ import annotations

import re
import time
import urllib.parse
from typing import Callable, Dict, List, Optional, Tuple

from playwright.sync_api import Page

from captcha_flow import is_captcha, wait_captcha_resolved, CaptchaHook
from utils import extract_phones, maybe_human_delay, RateLimiter
from logger import get_logger

_logger = get_logger()

INT_RE = re.compile(r"\d+")
RATING_A11Y_RE = re.compile(r"Рейтинг\s*([0-9]+(?:[.,][0-9]+)?)", re.IGNORECASE)


def _trace_click(action: str, detail: str = "") -> None:
    detail_msg = f" ({detail})" if detail else ""
    _logger.info("TRACE: click %s%s", action, detail_msg)


def _get_setting(settings_getter: Optional[Callable[[], object]], name: str, fallback):
    if settings_getter is None:
        return fallback
    try:
        settings = settings_getter()
    except Exception:
        return fallback
    if settings is None:
        return fallback
    if isinstance(settings, dict):
        return settings.get(name, fallback)
    return getattr(settings, name, fallback)


def _apply_rate_limiter_settings(
    rate_limiter: Optional[RateLimiter],
    settings_getter: Optional[Callable[[], object]],
    *,
    delay_min_s: float,
    delay_max_s: float,
    backoff_base_s: Optional[float] = None,
    backoff_max_s: Optional[float] = None,
) -> None:
    if rate_limiter is None or settings_getter is None:
        return
    min_s = float(_get_setting(settings_getter, "delay_min_s", delay_min_s) or 0.0)
    max_s = float(_get_setting(settings_getter, "delay_max_s", delay_max_s) or 0.0)
    rate_limiter.min_delay_s = max(0.0, min_s)
    rate_limiter.max_delay_s = max(rate_limiter.min_delay_s, max_s)
    if backoff_base_s is not None:
        rate_limiter.backoff_base_s = max(0.0, float(backoff_base_s))
    if backoff_max_s is not None:
        rate_limiter.backoff_max_s = max(0.0, float(backoff_max_s))


def build_serp_url(query: str, lr: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://yandex.ru/search/?lr={lr}&text={q}&serp-reload-from=companies&noreask=1"


def _normalize_href(href: str) -> str:
    if not href:
        return ""
    href = href.replace("&amp;", "&")
    if href.startswith("/"):
        return "https://yandex.ru" + href
    return href


def _strip_profile_link(href: str) -> str:
    if not href:
        return ""
    href = _normalize_href(href)
    try:
        parsed = urllib.parse.urlsplit(href)
    except Exception:
        return href
    if "yandex.ru" in parsed.netloc and parsed.path.startswith("/profile/"):
        parts = parsed.path.split("/")
        if len(parts) >= 3 and parts[2]:
            clean_path = "/".join(parts[:3])
        else:
            clean_path = parsed.path
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or "yandex.ru"
        return urllib.parse.urlunsplit((scheme, netloc, clean_path, "", ""))
    return href


def _safe_text(loc) -> str:
    try:
        if loc.count() > 0:
            return (loc.first.inner_text() or "").strip()
    except Exception:
        pass
    return ""


def _arrow_is_disabled(arrow) -> bool:
    """Return True if carousel right arrow is disabled/unavailable."""
    try:
        el = getattr(arrow, "element_handle", None)
        if callable(el):
            el = arrow.element_handle()
        if not el:
            try:
                el = arrow.first.element_handle()
            except Exception:
                el = None
        if not el:
            return True
        return bool(
            el.evaluate(
                """(node) => {
                    const cls = node.className || "";
                    if (cls.includes("disabled") || cls.includes("Disabled")) return true;
                    const aria = node.getAttribute("aria-disabled");
                    if (aria === "true") return true;
                    if (node.disabled === true) return true;
                    return false;
                }"""
            )
        )
    except Exception:
        return True


def _wait_for_card_growth(cards, stop_event, pause_event, timeout_s: float = 3.0) -> bool:
    start_count = cards.count()
    deadline = time.time() + timeout_s
    while time.time() < deadline and not stop_event.is_set():
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(0.1)
        if cards.count() > start_count:
            return True
        time.sleep(0.1)
    return False


def _wait_for_no_card_growth(cards, stop_event, pause_event, timeout_s: float = 5.0) -> None:
    start_count = cards.count()
    deadline = time.time() + timeout_s
    while time.time() < deadline and not stop_event.is_set():
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(0.1)
        if cards.count() != start_count:
            start_count = cards.count()
        time.sleep(0.1)


def _wait_for_carousel_arrow(
    page: Page,
    target_url: Optional[str],
    log: Callable[[str], None],
    timeout_ms: int = 30000,
    retries: int = 3,
):
    """Wait for carousel arrow to appear; reload if needed."""
    selector = (
        ".OrgsHorizontalList .Scroller-Arrow.ArrowButton_direction_right, "
        ".OrgsHorizontalList .ArrowButton.ArrowButton_direction_right"
    )
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            arrow = page.locator(selector).first
            arrow.wait_for(state="visible", timeout=timeout_ms)
            return arrow
        except Exception as e:
            last_err = e
            log(f"SERP: стрелка карусели не найдена (попытка {attempt}/{retries}). Перезагружаю...")
            try:
                if target_url:
                    page.goto(target_url, wait_until="domcontentloaded")
                else:
                    page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            try:
                page.wait_for_timeout(3000)
            except Exception:
                time.sleep(3)

    raise RuntimeError(f"SERP: не удалось дождаться стрелки карусели после {retries} попыток: {last_err}")


def _parse_rating(card) -> str:
    txt = _safe_text(card.locator(".LabelRating .Label-Content"))
    if txt:
        try:
            return str(float(txt.replace(",", ".")))
        except Exception:
            return txt.replace(",", ".")

    a11y = _safe_text(card.locator(".LabelRating .A11yHidden"))
    if a11y:
        m = RATING_A11Y_RE.search(a11y)
        if m:
            return m.group(1).replace(",", ".")
    return ""


def _parse_reviews(card) -> str:
    t = _safe_text(card.locator("a.OrgCard-ReviewsLink"))
    if not t:
        return ""
    m = INT_RE.search(t)
    return m.group(0) if m else ""


def _parse_badge_blue(card) -> bool:
    try:
        badge = card.locator(
            ".OrgCard-TitleWrapText .A11yHidden:has-text('Информация об организации подтверждена владельцем')"
        )
        return badge.count() > 0
    except Exception:
        return False


def _get_name_and_link(card) -> Tuple[str, str]:
    name = ""
    link = ""

    title_a = card.locator("a.OrgCard-Title").first
    if title_a.count() > 0:
        name = _safe_text(title_a.locator(".OrgCard-TitleText"))
        try:
            href = title_a.get_attribute("href") or ""
        except Exception:
            href = ""
        if href:
            link = _strip_profile_link(_normalize_href(href))

    return name, link


def _maybe_extract_phone_from_button(card) -> str:
    try:
        btn = card.locator("button:has-text('Показать телефон')").first
        if btn.count() == 0 or not btn.is_visible():
            return ""
        try:
            _trace_click("show phone", "playwright click")
            btn.click(timeout=1500, force=True)
        except Exception:
            try:
                _trace_click("show phone", "evaluate click")
                btn.evaluate("el => el.click()")
            except Exception:
                return ""
        time.sleep(0.1)
        try:
            text = (btn.locator(".Button-Text").first.inner_text(timeout=1500) or "").strip()
        except Exception:
            try:
                text = (btn.inner_text(timeout=1500) or "").strip()
            except Exception:
                text = ""
        phones = extract_phones(text)
        return ", ".join(phones) if phones else ""
    except Exception:
        return ""


def _extract_from_extra_popup(page: Page, card) -> Tuple[str, str]:
    try:
        btn = card.locator("button:has-text('Ещё')").first
        if btn.count() == 0:
            return "", ""
        popup = None
        for _ in range(2):
            try:
                card.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            try:
                _trace_click("more actions", "playwright click")
                btn.click(timeout=1500, force=True)
            except Exception:
                try:
                    _trace_click("more actions", "evaluate click")
                    btn.evaluate("el => el.click()")
                except Exception:
                    pass
            time.sleep(0.1)
            popup = page.locator(".OrgsListActions-PopupContent:visible").last
            if popup.count() > 0:
                break
        if not popup or popup.count() == 0:
            return "", ""
        time.sleep(0.5)
        phone_text = _safe_text(
            popup.locator(
                "button.OrgsListActions-ExtraButton:has(.OrgsListActions-Icon_type_phone) .Button-Text"
            )
        )
        phones = ", ".join(extract_phones(phone_text)) if phone_text else ""
        profile_link = ""
        try:
            route_anchor = popup.locator(
                "a.OrgsListActions-ExtraButton:has(.OrgsListActions-Icon_type_route), "
                "a.OrgsListActions-ExtraButton:has-text('Маршрут')"
            ).first
            if route_anchor.count() > 0:
                href = route_anchor.get_attribute("href") or ""
                href = _normalize_href(href)
                profile_link = _strip_profile_link(href)
        except Exception:
            profile_link = ""
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return phones, profile_link
    except Exception:
        return "", ""


def _extract_phone_and_profile(page: Page, card) -> Tuple[str, str]:
    button_phone = _maybe_extract_phone_from_button(card)
    popup_phone, profile_link = _extract_from_extra_popup(page, card)
    phones = popup_phone or button_phone
    return phones, profile_link


def parse_serp_cards(
    page: Page,
    *,
    max_clicks: int,
    arrow_delay_ms: int,
    card_delay_ms: int,
    phone_delay_ms: int,
    stop_event,
    pause_event,
    log: Callable[[str], None],
    captcha_resume_event,
    captcha_hook: Optional[CaptchaHook] = None,
    captcha_action_poll: Optional[Callable[[Page], Optional[Page]]] = None,
    progress: Optional[Callable[[dict], None]] = None,
    delay_min_s: float = 0.0,
    delay_max_s: float = 0.0,
    row_cb: Optional[Callable[[Dict, int, int], None]] = None,
    do_parse: bool = True,
    do_scroll: bool = True,
    rate_limiter: Optional[RateLimiter] = None,
    batch_every_n: int = 0,
    batch_pause_s: float = 0.0,
    start_index: int = 0,
    settings_getter: Optional[Callable[[], object]] = None,
) -> List[Dict]:
    """Parse organization cards in Yandex SERP."""
    if is_captcha(page):
        page = wait_captcha_resolved(
            page,
            log,
            stop_event,
            captcha_resume_event,
            hook=captcha_hook,
            action_poll=captcha_action_poll,
            rate_limiter=rate_limiter,
        )
        if page is None:
            return []

    def _setting_float(name: str, fallback: float) -> float:
        try:
            return float(_get_setting(settings_getter, name, fallback) or 0.0)
        except Exception:
            return float(fallback or 0.0)

    def _setting_int(name: str, fallback: int) -> int:
        try:
            return int(float(_get_setting(settings_getter, name, fallback) or 0))
        except Exception:
            return int(fallback or 0)

    if do_scroll:
        try:
            arrow = _wait_for_carousel_arrow(page, page.url, log, timeout_ms=3000, retries=1)
        except Exception:
            _logger.debug("SERP: arrow not found", exc_info=True)
            arrow = None

        selectors = [
            ".OrgCard",
            ".OrganicCard",
            ".Organic-Card",
            "li.OrgCard",
        ]
        cards = None
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if loc.count() > 0:
                    cards = loc
                    break
            except Exception:
                _logger.debug("SERP: card locator failed", exc_info=True)

        clicks = 0
        while arrow is not None and clicks < _setting_int("max_clicks", max_clicks) and not stop_event.is_set():
            while pause_event.is_set() and not stop_event.is_set():
                time.sleep(0.1)
            if is_captcha(page):
                page = wait_captcha_resolved(
                    page,
                    log,
                    stop_event,
                    captcha_resume_event,
                    hook=captcha_hook,
                    action_poll=captcha_action_poll,
                    rate_limiter=rate_limiter,
                )
                if page is None:
                    return []

            if _arrow_is_disabled(arrow):
                break
            try:
                _trace_click("carousel arrow", "playwright click")
                arrow.click(timeout=4000)
                clicks += 1
                if progress:
                    progress({"phase": "serp_scroll", "clicks": clicks})
            except Exception:
                _logger.debug("SERP: arrow click failed", exc_info=True)
                if rate_limiter is not None:
                    _apply_rate_limiter_settings(
                        rate_limiter,
                        settings_getter,
                        delay_min_s=_setting_float("delay_min_s", delay_min_s),
                        delay_max_s=_setting_float("delay_max_s", delay_max_s),
                        backoff_base_s=_setting_float("backoff_base_s", rate_limiter.backoff_base_s),
                        backoff_max_s=_setting_float("backoff_max_s", rate_limiter.backoff_max_s),
                    )
                    rate_limiter.wait_backoff(stop_event, pause_event)
                break

            try:
                page.wait_for_timeout(max(1, min(10, int(_setting_int("arrow_delay_ms", arrow_delay_ms)))))
            except Exception:
                time.sleep(0.01)

            grew = False
            if cards is not None:
                try:
                    grew = _wait_for_card_growth(cards, stop_event, pause_event)
                except Exception:
                    grew = False

            try:
                arrow_visible = arrow.count() > 0 and arrow.is_visible()
            except Exception:
                arrow_visible = False

            if not grew and not arrow_visible:
                break

            maybe_human_delay(
                stop_event,
                pause_event,
                _setting_float("delay_min_s", delay_min_s),
                _setting_float("delay_max_s", delay_max_s),
            )
            if rate_limiter is not None:
                _apply_rate_limiter_settings(
                    rate_limiter,
                    settings_getter,
                    delay_min_s=_setting_float("delay_min_s", delay_min_s),
                    delay_max_s=_setting_float("delay_max_s", delay_max_s),
                    backoff_base_s=_setting_float("backoff_base_s", rate_limiter.backoff_base_s),
                    backoff_max_s=_setting_float("backoff_max_s", rate_limiter.backoff_max_s),
                )
                rate_limiter.wait_action(stop_event, pause_event)

        if cards is not None:
            _wait_for_no_card_growth(cards, stop_event, pause_event, timeout_s=5.0)

    if not do_parse:
        return []

    selectors = [
        ".OrgCard",
        ".OrganicCard",
        ".Organic-Card",
        "li.OrgCard",
    ]
    cards = None
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                cards = loc
                break
        except Exception:
            _logger.debug("SERP: card locator failed", exc_info=True)

    if cards is None:
        log("SERP: карточки не найдены.")
        return []

    try:
        total = cards.count()
    except Exception:
        total = 0

    rows: List[Dict] = []
    for idx in range(total):
        if idx < start_index:
            continue
        if stop_event.is_set():
            break
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(0.1)

        if is_captcha(page):
            page = wait_captcha_resolved(
                page,
                log,
                stop_event,
                captcha_resume_event,
                hook=captcha_hook,
                action_poll=captcha_action_poll,
                rate_limiter=rate_limiter,
            )
            if page is None:
                break

        card = cards.nth(idx)
        name, link = _get_name_and_link(card)
        rating = _parse_rating(card)
        reviews = _parse_reviews(card)
        badge_blue = 1 if _parse_badge_blue(card) else 0

        time.sleep(0.01)
        try:
            phones, profile_link = _extract_phone_and_profile(page, card)
        except Exception:
            phones, profile_link = "", ""

        if not phones:
            try:
                text_blob = (card.inner_text(timeout=1500) or "").strip()
                phones = ", ".join(extract_phones(text_blob))
            except Exception:
                _logger.debug("SERP: phone extraction failed", exc_info=True)

        try:
            page.wait_for_timeout(max(5, int(_setting_int("phone_delay_ms", phone_delay_ms))))
        except Exception:
            time.sleep(max(0.01, float(_setting_int("phone_delay_ms", phone_delay_ms)) / 1000.0))

        row = {
            "name": name,
            "rating": rating,
            "reviews": reviews,
            "good_place": "",
            "telegram": "",
            "vk": "",
            "badge_blue": badge_blue,
            "badge_green": "",
            "phones": phones,
            "url": profile_link or link,
        }
        rows.append(row)

        if row_cb:
            try:
                row_cb(row, idx + 1, total)
            except Exception:
                _logger.debug("SERP: row_cb failed", exc_info=True)

        if progress:
            progress({"phase": "serp_parse", "index": idx + 1, "total": total, "rows": len(rows)})

        maybe_human_delay(
            stop_event,
            pause_event,
            _setting_float("delay_min_s", delay_min_s),
            _setting_float("delay_max_s", delay_max_s),
        )

        if rate_limiter is not None:
            _apply_rate_limiter_settings(
                rate_limiter,
                settings_getter,
                delay_min_s=_setting_float("delay_min_s", delay_min_s),
                delay_max_s=_setting_float("delay_max_s", delay_max_s),
                backoff_base_s=_setting_float("backoff_base_s", rate_limiter.backoff_base_s),
                backoff_max_s=_setting_float("backoff_max_s", rate_limiter.backoff_max_s),
            )
            rate_limiter.maybe_batch_pause(
                idx + 1,
                _setting_int("batch_every_n", batch_every_n),
                _setting_float("batch_pause_s", batch_pause_s),
                stop_event,
                pause_event,
            )
            rate_limiter.wait_action(stop_event, pause_event)

    return rows
