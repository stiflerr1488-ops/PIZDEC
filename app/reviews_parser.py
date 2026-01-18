from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Generator, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.captcha_utils import CaptchaFlowHelper, is_captcha, wait_captcha_resolved, CaptchaHook
from app.playwright_utils import setup_resource_blocking
from app.utils import sanitize_text


LOGGER = logging.getLogger(__name__)

ORG_ID_RE = re.compile(r"/maps/org(?:/[^/]+)?/(\d+)")


@dataclass
class Review:
    user_name: str = ""
    user_profile_url: str = ""
    rating: int = 0
    review_date: str = ""
    review_text: str = ""
    response_date: str = ""
    response_text: str = ""


class YandexReviewsParser:
    scroll_container_selector = "div.scroll__container"
    review_selector = "div.business-review-view"
    expand_selector = "div.business-review-view__expand"
    user_selector = "a.business-review-view__link"
    rating_selector = "div.business-rating-badge-view__stars"
    rating_full_selector = "div.business-rating-badge-view__stars ._full"
    review_date_selector = "span.business-review-view__date"
    review_text_selector = "div.business-review-view__body"
    response_date_selector = "span.business-review-comment-content__date"
    response_text_selector = "div.business-review-comment-content__bubble"
    max_scroll_idle_time = 10

    def __init__(
        self,
        url: str,
        *,
        headless: bool = False,
        block_images: bool = False,
        block_media: bool = False,
        stop_event=None,
        pause_event=None,
        captcha_resume_event=None,
        captcha_hook: Optional[CaptchaHook] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.url = self._normalize_url(url)
        self.headless = headless
        self.block_images = block_images
        self.block_media = block_media
        self.stop_event = stop_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.captcha_resume_event = captcha_resume_event or threading.Event()
        self.captcha_hook = captcha_hook
        self._log_cb = log
        self.total_reviews = 0

    @staticmethod
    def _normalize_url(raw: str) -> str:
        cleaned = (raw or "").strip()
        if not cleaned:
            return ""
        if cleaned.isdigit():
            return f"https://yandex.ru/maps/org/{cleaned}/"
        if cleaned.startswith("//"):
            cleaned = f"https:{cleaned}"
        if cleaned.startswith("yandex.ru"):
            cleaned = f"https://{cleaned}"
        match = ORG_ID_RE.search(cleaned)
        if match:
            org_id = match.group(1)
            return f"https://yandex.ru/maps/org/{org_id}/"
        return cleaned

    def run(self) -> Generator[Review, None, None]:
        if not self.url:
            return
        self._log("Открываю карточку организации: %s", self.url)
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--window-size=1700,900", "--disable-blink-features=AutomationControlled"],
                channel="chrome",
            )
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
            viewport = {"width": 1700, "height": 900}
            context = browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                is_mobile=False,
                has_touch=False,
                device_scale_factor=1,
            )
            setup_resource_blocking(context, self.block_images, self.block_media)
            page = context.new_page()
            page.set_default_timeout(20000)

            page.goto(self.url, wait_until="domcontentloaded")
            captcha_helper = CaptchaFlowHelper(
                playwright=p,
                base_context=context,
                base_page=page,
                headless=self.headless,
                block_images=self.block_images,
                block_media=self.block_media,
                log=self._log,
                hook=self.captcha_hook,
                user_agent=user_agent,
                viewport=viewport,
            )
            self._captcha_action_poll = captcha_helper.poll
            try:
                page = self._ensure_no_captcha(page)
                if page is None:
                    return

                self._close_popups(page)
                page = self._ensure_no_captcha(page)
                if page is None:
                    return

                self._scroll_reviews(page)
                page = self._ensure_no_captcha(page)
                if page is None:
                    return

                self.total_reviews = page.locator(self.review_selector).count()
                self._log("Найдено отзывов: %s", self.total_reviews)

                reviews = page.locator(self.review_selector)
                for index in range(self.total_reviews):
                    if self.stop_event.is_set():
                        return
                    while self.pause_event.is_set() and not self.stop_event.is_set():
                        time.sleep(0.1)
                    page = self._ensure_no_captcha(page)
                    if page is None:
                        return

                    review_loc = reviews.nth(index)
                    self._expand_review(review_loc)
                    review = self._parse_review(review_loc)
                    yield review
                    if not self._wait_between_reviews(1.0):
                        return
            finally:
                try:
                    captcha_helper.close()
                except Exception:
                    LOGGER.debug("Failed to close captcha helper", exc_info=True)
                try:
                    context.close()
                except Exception:
                    LOGGER.debug("Failed to close browser context", exc_info=True)
                try:
                    browser.close()
                except Exception:
                    LOGGER.debug("Failed to close browser", exc_info=True)

    def _log(self, message: str, *args) -> None:
        if self._log_cb:
            try:
                self._log_cb(message % args if args else message)
                return
            except Exception:
                pass
        LOGGER.info(message, *args)

    def _ensure_no_captcha(self, page: Page) -> Optional[Page]:
        if self.stop_event.is_set():
            return None
        if is_captcha(page):
            return wait_captcha_resolved(
                page,
                self._log,
                self.stop_event,
                self.captcha_resume_event,
                hook=self.captcha_hook,
                action_poll=getattr(self, "_captcha_action_poll", None),
            )
        return page

    def _close_popups(self, page: Page) -> None:
        selectors = [
            "button:has-text('Принять')",
            "button:has-text('Согласен')",
            "button:has-text('Отклонить')",
            "button:has-text('Закрыть')",
        ]
        for selector in selectors:
            try:
                page.locator(selector).first.click(timeout=2000)
                time.sleep(0.2)
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

    def _scroll_reviews(self, page: Page) -> None:
        self._log("Прокручиваю страницу для загрузки отзывов…")
        last_count = 0
        last_new_time = time.monotonic()
        while True:
            if self.stop_event.is_set():
                return
            while self.pause_event.is_set() and not self.stop_event.is_set():
                time.sleep(0.1)

            current_count = page.locator(self.review_selector).count()
            if current_count > last_count:
                last_count = current_count
                last_new_time = time.monotonic()

            if time.monotonic() - last_new_time >= self.max_scroll_idle_time:
                self._log("Новые отзывы не появляются %.0f сек — начинаю парсинг.", self.max_scroll_idle_time)
                break

            moved = self._scroll_container(page, step=1200)
            if not moved:
                time.sleep(0.3)
            else:
                time.sleep(0.2)

    def _scroll_container(self, page: Page, step: int) -> bool:
        try:
            result = page.evaluate(
                """
                ({selector, scrollStep}) => {
                  const container = document.querySelector(selector);
                  if (!container) {
                    window.scrollBy(0, scrollStep);
                    return { moved: true, scrollTop: window.scrollY, maxTop: document.body.scrollHeight };
                  }
                  const prevTop = container.scrollTop;
                  const maxTop = container.scrollHeight - container.clientHeight;
                  const nextTop = Math.min(prevTop + scrollStep, maxTop);
                  container.scrollTop = nextTop;
                  container.dispatchEvent(new Event("scroll", { bubbles: true }));
                  return { moved: nextTop > prevTop, scrollTop: nextTop, maxTop };
                }
                """,
                {"selector": self.scroll_container_selector, "scrollStep": step},
            )
            return bool(result.get("moved")) if isinstance(result, dict) else False
        except Exception:
            return False

    def _expand_review(self, review_loc) -> None:
        try:
            expand = review_loc.locator(self.expand_selector)
            if expand.count() > 0:
                expand.first.evaluate("el => el.click()")
        except Exception:
            return

    def _parse_review(self, review_loc) -> Review:
        user_name = ""
        user_profile_url = ""
        try:
            user_link = review_loc.locator(self.user_selector).first
            if user_link.count() > 0:
                user_name = sanitize_text(user_link.text_content())
                user_profile_url = sanitize_text(user_link.get_attribute("href"))
        except Exception:
            pass

        rating = 0
        try:
            rating = review_loc.locator(self.rating_full_selector).count()
        except Exception:
            rating = 0

        review_date = ""
        try:
            date_loc = review_loc.locator(self.review_date_selector).first
            if date_loc.count() > 0:
                review_date = sanitize_text(date_loc.get_attribute("content"))
                if not review_date:
                    review_date = sanitize_text(date_loc.text_content())
        except Exception:
            pass

        review_text = ""
        try:
            body_loc = review_loc.locator(self.review_text_selector).first
            if body_loc.count() > 0:
                review_text = sanitize_text(body_loc.text_content())
        except Exception:
            pass

        response_date = ""
        try:
            response_date_loc = review_loc.locator(self.response_date_selector).first
            if response_date_loc.count() > 0:
                response_date = sanitize_text(response_date_loc.text_content())
        except Exception:
            pass

        response_text = ""
        try:
            response_text_loc = review_loc.locator(self.response_text_selector).first
            if response_text_loc.count() > 0:
                response_text = sanitize_text(response_text_loc.text_content())
        except Exception:
            pass

        return Review(
            user_name=user_name,
            user_profile_url=user_profile_url,
            rating=rating,
            review_date=review_date,
            review_text=review_text,
            response_date=response_date,
            response_text=response_text,
        )

    def _wait_between_reviews(self, seconds: float) -> bool:
        end_time = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end_time:
            if self.stop_event.is_set():
                return False
            if self.pause_event.is_set():
                time.sleep(0.1)
                continue
            time.sleep(0.05)
        return True
