from __future__ import annotations

import re
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from playwright.sync_api import Page, sync_playwright

from excel_writer import ExcelWriter
from filters import passes_potential_filters
from notifications import notify_sound
from playwright_utils import apply_stealth, setup_resource_blocking
from settings_model import Settings
from utils import extract_phones, get_logger, maybe_human_delay, RateLimiter
from pacser_maps import Organization

CaptchaHook = Callable[[str, Page], None]
CaptchaActionPoll = Callable[[Page], Optional[Page]]
# stage values: "detected" | "still" | "cleared"

_logger = get_logger()


def is_captcha(page: Page) -> bool:
    """Best-effort detection of Yandex captcha pages.

    We do NOT try to bypass captcha; only detect it and allow user to solve it manually.
    """
    try:
        u = (page.url or "").lower()
        if "showcaptcha" in u or "/captcha" in u or "captcha" in u:
            return True
    except Exception:
        _logger.debug("Captcha URL check failed", exc_info=True)
    try:
        t = (page.title() or "").lower()
        if "вы не робот" in t or "капча" in t or "captcha" in t:
            return True
    except Exception:
        _logger.debug("Captcha title check failed", exc_info=True)
    try:
        selectors = [
            "input[name='rep']",
            "form[action*='captcha']",
            "div[class*='captcha']",
            "text=Введите символы",
            "text=Подтвердите, что запросы отправляли вы",
        ]
        for selector in selectors:
            loc = page.locator(selector)
            if loc.count() > 0:
                return True
    except Exception:
        _logger.debug("Captcha selector check failed", exc_info=True)
    return False


def wait_captcha_resolved(
    page: Page,
    log: Callable[[str], None],
    stop_event,
    captcha_resume_event,
    hook: Optional[CaptchaHook] = None,
    action_poll: Optional[CaptchaActionPoll] = None,
    poll_s: float = 0.2,
    rate_limiter: Optional[RateLimiter] = None,
) -> Optional[Page]:
    """Wait until captcha disappears AND user confirms in GUI.

    Flow:
      1) Detect captcha -> hook("detected")
      2) User solves captcha in a visible browser and presses GUI button -> captcha_resume_event.set()
      3) We re-check the page. If captcha still present -> hook("still") and keep waiting.

    Returns:
      Page - captcha gone (we can continue)
      None - stop requested
    """
    log("🧩 Обнаружена капча. Реши её в браузере и нажми кнопку 'Капча пройдена' в GUI.")
    if hook:
        try:
            hook("detected", page)
        except Exception:
            _logger.debug("Captcha hook error (detected)", exc_info=True)

    # IMPORTANT: in Playwright Sync API, using bare time.sleep() while request interception is
    # enabled can make the browser *look like it has no internet*, because the Python thread
    # is not yielding to the Playwright dispatcher frequently enough.
    #
    # To keep the browser responsive during captcha, we prefer page.wait_for_timeout(), and
    # fall back to time.sleep() only if needed.
    captcha_resume_event.clear()
    while not stop_event.is_set():
        # Allow UI to request helper actions (focus/reload/network check)
        if action_poll is not None:
            try:
                maybe_page = action_poll(page)
                if maybe_page is not None:
                    page = maybe_page
            except Exception:
                _logger.debug("Captcha action poll error", exc_info=True)

        if captcha_resume_event.is_set():
            captcha_resume_event.clear()
            try:
                # Give the page a moment to navigate/finish after user actions.
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass

                if not is_captcha(page):
                    log("✅ Капча снята. Продолжаю.")
                    if hook:
                        try:
                            hook("cleared", page)
                        except Exception:
                            _logger.debug("Captcha hook error (cleared)", exc_info=True)
                    if action_poll is not None:
                        try:
                            maybe_page = action_poll(page)
                            if maybe_page is not None:
                                page = maybe_page
                        except Exception:
                            _logger.debug("Captcha action poll error (cleared)", exc_info=True)
                    if rate_limiter is not None:
                        rate_limiter.wait_backoff(stop_event, None)
                    return page

                log("⚠️ Капча всё ещё активна. Реши её и нажми кнопку ещё раз.")
                if hook:
                    try:
                        hook("still", page)
                    except Exception:
                        _logger.debug("Captcha hook error (still)", exc_info=True)
            except Exception:
                # In doubt: keep waiting, user can press again.
                _logger.debug("Captcha wait loop error", exc_info=True)

        # Yield to Playwright so the browser keeps loading pages normally.
        sleep_s = max(0.05, float(poll_s))
        try:
            page.wait_for_timeout(int(sleep_s * 1000))
        except Exception:
            time.sleep(sleep_s)
    return None

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


def _wait_for_card_growth_fast(
    cards,
    stop_event,
    pause_event,
    timeout_s: float = 0.25,
    poll_s: float = 0.05,
) -> bool:
    start_count = cards.count()
    deadline = time.time() + timeout_s
    while time.time() < deadline and not stop_event.is_set():
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(0.05)
        if cards.count() > start_count:
            return True
        time.sleep(poll_s)
    return False


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


def _extract_oid_from_href(href: str) -> str:
    href = _normalize_href(href)
    if not href:
        return ""
    try:
        parsed = urllib.parse.urlsplit(href)
    except Exception:
        return ""
    if parsed.path.startswith("/profile/"):
        parts = parsed.path.split("/")
        if len(parts) >= 3 and parts[2]:
            return parts[2]
    try:
        params = urllib.parse.parse_qs(parsed.query)
        oid_val = params.get("oid", [""])[0]
        if isinstance(oid_val, str) and oid_val:
            if ":" in oid_val:
                oid_val = oid_val.split(":", 1)[-1]
            return oid_val
    except Exception:
        pass
    return ""


def _build_profile_url(oid: str) -> str:
    if not oid:
        return ""
    return f"https://yandex.ru/profile/{oid}"


def _extract_from_extra_popup(page: Page, card) -> Tuple[str, str, str]:
    try:
        btn = card.locator("button:has-text('Ещё')").first
        if btn.count() == 0:
            return "", "", ""
        popup = None
        for _ in range(2):
            try:
                card.scroll_into_view_if_needed(timeout=500)
            except Exception:
                pass
            try:
                _trace_click("more actions", "playwright click")
                btn.click(timeout=800, force=True)
            except Exception:
                try:
                    _trace_click("more actions", "evaluate click")
                    btn.evaluate("el => el.click()")
                except Exception:
                    pass
            try:
                page.wait_for_timeout(200)
            except Exception:
                time.sleep(0.2)
            popup = page.locator(".Popup2_visible.OrgsListActions-PopupContent").last
            if popup.count() > 0:
                break
        if not popup or popup.count() == 0:
            return "", "", ""
        phone_text = _safe_text(
            popup.locator(
                "button.OrgsListActions-ExtraButton:has(.OrgsListActions-Icon_type_phone) .Button-Text"
            )
        )
        phones = ", ".join(extract_phones(phone_text)) if phone_text else ""
        profile_link = ""
        site_link = ""
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
            site_anchor = popup.locator(
                "a.OrgsListActions-ExtraButton:has(.OrgsListActions-Icon_type_site)"
            ).first
            if site_anchor.count() > 0:
                site_href = site_anchor.get_attribute("href") or ""
                site_link = _normalize_href(site_href)
        except Exception:
            site_link = ""
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return phones, profile_link, site_link
    except Exception:
        return "", "", ""


def _extract_action_main(card) -> Tuple[str, str]:
    text = ""
    href = ""
    try:
        btn = card.locator(".OrgsListActions-FirstMainButton").first
        if btn.count() > 0:
            text = _safe_text(btn.locator(".Button-Text")) or _safe_text(btn)
            try:
                href = _normalize_href(btn.get_attribute("href") or "")
            except Exception:
                href = ""
    except Exception:
        pass
    if not href:
        try:
            link = card.locator(".OrgsListActions a.Button_link").first
            if link.count() > 0:
                href = _normalize_href(link.get_attribute("href") or "")
                if not text:
                    text = _safe_text(link.locator(".Button-Text")) or _safe_text(link)
        except Exception:
            pass
    return text, href


def _extract_phone_from_main_button(card) -> str:
    text, _ = _extract_action_main(card)
    if not text:
        return ""
    phones = extract_phones(text)
    return ", ".join(phones) if phones else ""


def _click_show_phone(card, page: Page) -> str:
    try:
        btn = card.locator(".OrgsListActions-FirstMainButton").first
        if btn.count() == 0:
            btn = card.locator("button:has-text('Показать телефон')").first
        if btn.count() == 0:
            return ""
        text_before = _safe_text(btn.locator(".Button-Text")) or _safe_text(btn)
        if "Показать телефон" not in text_before:
            return ""
        try:
            _trace_click("show phone", "playwright click")
            btn.click(timeout=800, force=True)
        except Exception:
            try:
                _trace_click("show phone", "evaluate click")
                btn.evaluate("el => el.click()")
            except Exception:
                return ""
        try:
            page.wait_for_timeout(200)
        except Exception:
            time.sleep(0.2)
        text_after = _safe_text(btn.locator(".Button-Text")) or _safe_text(btn)
        phones = extract_phones(text_after)
        return ", ".join(phones) if phones else ""
    except Exception:
        return ""


def _extract_card_site(card) -> str:
    _, href = _extract_action_main(card)
    return href


def _extract_card_url_from_card(card, fallback_link: str) -> str:
    link = fallback_link or ""
    try:
        title_link = card.locator("a.OrgCard-Title").first
        if title_link.count() > 0:
            link = _normalize_href(title_link.get_attribute("href") or "") or link
    except Exception:
        pass
    oid = _extract_oid_from_href(link)
    return _build_profile_url(oid)


def _load_all_cards(page: Page, stop_event, pause_event, log: Callable[[str], None]):
    selectors = [
        ".OrgCard",
        ".OrganicCard",
        ".Organic-Card",
        "li.OrgCard",
        ".OrgCard-Body",
    ]
    cards = None
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() > 0:
                cards = loc
                break
        except Exception:
            _logger.debug("SERP: card locator failed for %s", sel, exc_info=True)
    if cards is None:
        log("SERP: карточки не найдены.")
        return None

    arrow_selector = (
        ".Scroller-Arrow.ArrowButton_direction_right, "
        ".ArrowButton.ArrowButton_direction_right"
    )
    shadow_selector = ".Scroller-ArrowShadow.Scroller-ArrowShadow_direction_right"
    stalled = 0
    last_count = cards.count()
    log("SERP: загрузка всех карточек...")

    while not stop_event.is_set():
        while pause_event.is_set() and not stop_event.is_set():
            time.sleep(0.05)

        arrow = page.locator(arrow_selector).first
        try:
            arrow_visible = arrow.count() > 0 and arrow.is_visible()
        except Exception:
            arrow_visible = False
        try:
            shadow_visible = page.locator(shadow_selector).count() > 0
        except Exception:
            shadow_visible = False

        if not arrow_visible and not shadow_visible and stalled >= 2:
            break

        if arrow_visible:
            try:
                _trace_click("carousel arrow", "playwright click")
                arrow.click(timeout=800)
            except Exception:
                _logger.debug("SERP: arrow click failed", exc_info=True)

        grew = _wait_for_card_growth_fast(cards, stop_event, pause_event, timeout_s=0.2)
        try:
            current_count = cards.count()
        except Exception:
            current_count = last_count

        if grew or current_count > last_count:
            stalled = 0
            last_count = current_count
        else:
            stalled += 1

        try:
            page.wait_for_timeout(200)
        except Exception:
            time.sleep(0.2)

        if stalled >= 3 and not shadow_visible:
            break

    log(f"SERP: карточек найдено {last_count}.")
    return cards


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
        cards = _load_all_cards(page, stop_event, pause_event, log)
    else:
        cards = None
        selectors = [
            ".OrgCard",
            ".OrganicCard",
            ".Organic-Card",
            "li.OrgCard",
            ".OrgCard-Body",
        ]
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

    if not do_parse:
        return []

    try:
        total = cards.count()
    except Exception:
        total = 0

    rows: List[Dict] = []
    seen_keys: set[str] = set()
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
        verified = (
            _parse_badge_blue(card)
            or card.locator(".OrgCard-TitleVerified, .Icon_type_verified").count() > 0
            or card.locator(".A11yHidden:has-text('подтверждена владельцем')").count() > 0
        )
        website = _extract_card_site(card)
        card_url = _extract_card_url_from_card(card, link)

        phones = _extract_phone_from_main_button(card)
        if not phones:
            phones = _click_show_phone(card, page)

        profile_link = ""
        need_popup = not phones or not card_url or not website
        if need_popup:
            popup_phone, popup_profile, popup_site = _extract_from_extra_popup(page, card)
            if not phones:
                phones = popup_phone
            if not profile_link:
                profile_link = popup_profile
            if not website:
                website = popup_site

        if profile_link:
            card_url = profile_link
        if not phones:
            _logger.debug("SERP: phone not found for card %s (%s)", idx + 1, name)
        if not card_url:
            _logger.debug("SERP: card_url not found for card %s (%s)", idx + 1, name)

        oid = _extract_oid_from_href(card_url) if card_url else ""
        dedupe_key = oid or f"{name}|{reviews}"
        if dedupe_key in seen_keys:
            _logger.debug("SERP: duplicate card skipped %s", dedupe_key)
            continue
        seen_keys.add(dedupe_key)

        row = {
            "name": name,
            "rating": rating,
            "reviews": reviews,
            "good_place": "",
            "telegram": "",
            "vk": "",
            "badge_blue": 1 if verified else 0,
            "badge_green": "",
            "phones": phones,
            "website": website,
            "url": card_url,
        }
        rows.append(row)

        if row_cb:
            try:
                row_cb(row, idx + 1, total)
            except Exception:
                _logger.debug("SERP: row_cb failed", exc_info=True)

        if progress:
            progress({"phase": "serp_parse", "index": idx + 1, "total": total, "rows": len(rows)})

        _logger.debug(
            "SERP: card %s/%s name=%s phone=%s site=%s url=%s",
            idx + 1,
            total,
            name,
            "yes" if phones else "no",
            "yes" if website else "no",
            "yes" if card_url else "no",
        )

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
            website=row.get("website", ""),
            card_url=row.get("url", ""),
            rating=row.get("rating", ""),
            rating_count=row.get("reviews", ""),
        )
        organizations.append(org)
    return organizations


def run_fast_parser(
    *,
    query: str,
    full_output_path: Path,
    potential_output_path: Path,
    lr: str,
    max_clicks: int,
    delay_min_s: float,
    delay_max_s: float,
    stop_event,
    pause_event,
    captcha_resume_event,
    log: Callable[[str], None],
    progress: Optional[Callable[[dict], None]] = None,
    settings: Optional[Settings] = None,
) -> int:
    url = build_serp_url(query, lr)
    log(f"быстрый: открываю поиск → {url}")
    rate_limiter = RateLimiter(min_delay_s=delay_min_s, max_delay_s=delay_max_s)

    with sync_playwright() as p:
        headless = settings.program.headless if settings else False
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        if settings:
            setup_resource_blocking(
                context,
                settings.program.block_images,
                settings.program.block_media,
            )
        page = context.new_page()
        if settings and settings.program.stealth:
            apply_stealth(context, page)
        page.set_default_timeout(20000)
        page.goto(url, wait_until="domcontentloaded")

        def _captcha_hook(stage: str, _page: Page) -> None:
            if settings and stage == "detected":
                notify_sound("captcha", settings)

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
            captcha_hook=_captcha_hook if settings else None,
            progress=progress,
            delay_min_s=delay_min_s,
            delay_max_s=delay_max_s,
            rate_limiter=rate_limiter,
        )

        organizations = _rows_to_organizations(rows)
        writer = ExcelWriter(full_output_path, potential_output_path)
        try:
            for org in organizations:
                if stop_event.is_set():
                    break
                include = passes_potential_filters(org, settings) if settings else True
                writer.append(org, include_in_potential=include)
        finally:
            writer.close()
            context.close()
            browser.close()
    return len(organizations)
