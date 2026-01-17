from __future__ import annotations

import time
from typing import Callable, Optional

from playwright.sync_api import Page

from playwright_utils import apply_stealth
from utils import get_logger, RateLimiter

CaptchaHook = Callable[[str, Page], None]
CaptchaActionPoll = Callable[[str, Page], Optional[Page]]
# stage values: "detected" | "manual" | "still" | "cleared" | "poll"

_logger = get_logger()

CAPTCHA_BUTTON_SELECTOR = "input#js-button.CheckboxCaptcha-Button"


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
    """Wait until captcha disappears (auto-check).

    Flow:
      1) Detect captcha -> hook("detected")
      2) User solves captcha in a visible browser; we keep polling.
      3) If captcha still present -> hook("still") and keep waiting.

    Returns:
      Page - captcha gone (we can continue)
      None - stop requested
    """
    if action_poll is not None:
        try:
            maybe_page = action_poll("detected", page)
            if maybe_page is not None:
                page = maybe_page
        except Exception:
            _logger.debug("Captcha action poll error (detected)", exc_info=True)

    log("🧩 Обнаружена капча. Реши её в браузере — статус проверяется автоматически.")
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
        if action_poll is not None:
            try:
                maybe_page = action_poll("poll", page)
                if maybe_page is not None:
                    page = maybe_page
            except Exception:
                _logger.debug("Captcha action poll error", exc_info=True)

        should_check = captcha_resume_event.is_set()
        if not should_check:
            try:
                should_check = not is_captcha(page)
            except Exception:
                _logger.debug("Captcha check failed", exc_info=True)

        if should_check:
            captcha_resume_event.clear()
            try:
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
                            maybe_page = action_poll("cleared", page)
                            if maybe_page is not None:
                                page = maybe_page
                        except Exception:
                            _logger.debug("Captcha action poll error (cleared)", exc_info=True)
                    if rate_limiter is not None:
                        rate_limiter.wait_backoff(stop_event, None)
                    return page

                log("⚠️ Капча всё ещё активна. Реши её, я продолжаю проверять.")
                if hook:
                    try:
                        hook("still", page)
                    except Exception:
                        _logger.debug("Captcha hook error (still)", exc_info=True)
                if action_poll is not None:
                    try:
                        maybe_page = action_poll("still", page)
                        if maybe_page is not None:
                            page = maybe_page
                    except Exception:
                        _logger.debug("Captcha action poll error (still)", exc_info=True)
            except Exception:
                _logger.debug("Captcha wait loop error", exc_info=True)

        sleep_s = max(0.05, float(poll_s))
        try:
            page.wait_for_timeout(int(sleep_s * 1000))
        except Exception:
            time.sleep(sleep_s)
    return None


def _reload_captcha_page(page: Page, log: Callable[[str], None]) -> None:
    log("🧩 Капча: перезагружаю страницу.")
    try:
        page.evaluate("window.stop && window.stop()")
    except Exception:
        _logger.debug("Captcha: window.stop failed", exc_info=True)
    try:
        page.reload(wait_until="domcontentloaded", timeout=20000)
    except Exception:
        _logger.debug("Captcha: reload failed", exc_info=True)


def _click_captcha_button(page: Page, log: Callable[[str], None]) -> None:
    log("🧩 Капча: нажимаю кнопку загрузки капчи.")
    try:
        locator = page.locator(CAPTCHA_BUTTON_SELECTOR)
        if locator.count() > 0:
            locator.first.click(timeout=3000)
            return
    except Exception:
        _logger.debug("Captcha: selector click failed", exc_info=True)
    try:
        page.click(CAPTCHA_BUTTON_SELECTOR, timeout=3000)
    except Exception:
        _logger.debug("Captcha: button click fallback failed", exc_info=True)


class CaptchaFlowHelper:
    def __init__(
        self,
        *,
        playwright,
        base_context,
        base_page: Page,
        headless: bool,
        stealth: bool,
        log: Callable[[str], None],
        hook: Optional[CaptchaHook],
        user_agent: str,
        viewport: dict,
        headers: Optional[dict] = None,
    ) -> None:
        self._playwright = playwright
        self._base_context = base_context
        self._base_page = base_page
        self._headless = headless
        self._stealth = stealth
        self._log = log
        self._hook = hook
        self._user_agent = user_agent
        self._viewport = viewport
        self._headers = headers or {}
        self._initialized = False
        self._using_visible = False
        self._visible_browser = None
        self._visible_context = None

    @staticmethod
    def init(**kwargs) -> "CaptchaFlowHelper":
        return CaptchaFlowHelper(**kwargs)

    def _wait_seconds(self, seconds: float, page: Page) -> None:
        try:
            page.wait_for_timeout(int(seconds * 1000))
        except Exception:
            time.sleep(seconds)

    def _open_visible_browser(self, page: Page) -> Optional[Page]:
        try:
            cookies = self._base_context.cookies()
        except Exception:
            cookies = []
        browser = self._playwright.chromium.launch(headless=False)
        context_kwargs = {
            "user_agent": self._user_agent,
            "viewport": self._viewport,
        }
        if self._headers:
            context_kwargs["extra_http_headers"] = self._headers
        context = browser.new_context(**context_kwargs)
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception:
                _logger.debug("Captcha: failed to add cookies to visible context", exc_info=True)
        visible_page = context.new_page()
        if self._stealth:
            apply_stealth(context, visible_page)
        visible_page.set_default_timeout(20000)
        try:
            visible_page.goto(page.url, wait_until="domcontentloaded")
        except Exception:
            _logger.debug("Captcha: visible page navigation failed", exc_info=True)
        self._visible_browser = browser
        self._visible_context = context
        self._using_visible = True
        return visible_page

    def _swap_back_to_headless(self) -> Optional[Page]:
        if not self._using_visible or not self._visible_context:
            return None
        try:
            cookies = self._visible_context.cookies()
            if cookies:
                self._base_context.add_cookies(cookies)
        except Exception:
            _logger.debug("Captcha: failed to sync cookies back to headless", exc_info=True)
        try:
            self._visible_context.close()
        except Exception:
            _logger.debug("Captcha: failed to close visible context", exc_info=True)
        if self._visible_browser is not None:
            try:
                self._visible_browser.close()
            except Exception:
                _logger.debug("Captcha: failed to close visible browser", exc_info=True)
        self._visible_context = None
        self._visible_browser = None
        self._using_visible = False
        try:
            self._base_page.reload(wait_until="domcontentloaded", timeout=20000)
        except Exception:
            _logger.debug("Captcha: reload headless page failed", exc_info=True)
        return self._base_page

    def poll(self, stage: str, page: Page) -> Optional[Page]:
        if stage == "detected" and not self._initialized:
            self._initialized = True
            _click_captcha_button(page, self._log)
            _reload_captcha_page(page, self._log)
            _click_captcha_button(page, self._log)
            _reload_captcha_page(page, self._log)
            if self._headless:
                self._wait_seconds(5.0, page)
                if is_captcha(page):
                    if self._hook:
                        try:
                            self._hook("manual", page)
                        except Exception:
                            _logger.debug("Captcha hook error (manual)", exc_info=True)
                    self._log("🧩 Капча снова появилась. Открываю браузер для ручного решения.")
                    visible_page = self._open_visible_browser(page)
                    if visible_page is not None:
                        _click_captcha_button(visible_page, self._log)
                        return visible_page
        if stage == "cleared" and self._using_visible:
            return self._swap_back_to_headless()
        return None

    def close(self) -> None:
        if self._visible_context is not None:
            try:
                self._visible_context.close()
            except Exception:
                _logger.debug("Captcha: failed to close visible context", exc_info=True)
        if self._visible_browser is not None:
            try:
                self._visible_browser.close()
            except Exception:
                _logger.debug("Captcha: failed to close visible browser", exc_info=True)
        self._visible_context = None
        self._visible_browser = None
        self._using_visible = False
