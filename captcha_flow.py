from __future__ import annotations

import time
from typing import Callable, Optional

from playwright.sync_api import Page

from logger import get_logger
from utils import RateLimiter

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
