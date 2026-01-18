from __future__ import annotations

import logging
import re
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Generator, Optional
from urllib.parse import quote

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.captcha_utils import CaptchaFlowHelper, is_captcha, wait_captcha_resolved, CaptchaHook
from app.playwright_utils import setup_resource_blocking
from app.utils import extract_count, human_delay, normalize_rating, sanitize_text


LOGGER = logging.getLogger(__name__)


@dataclass
class Organization:
    name: str = ""
    phone: str = ""
    verified: str = ""
    award: str = ""
    vk: str = ""
    telegram: str = ""
    whatsapp: str = ""
    website: str = ""
    card_url: str = ""
    rating: str = ""
    rating_count: str = ""


class YandexMapsScraper:
    base_url = "https://yandex.ru/web-maps/"
    scroll_container_selector = "div.scroll__container"
    list_item_selector = (
        "div.search-snippet-view__body[data-object='search-list-item'][data-id]"
    )
    list_item_wrapper_selector = (
        "div.search-snippet-view__body-button-wrapper[role='button'][tabindex='0']"
    )
    max_scroll_idle_time = 10

    def __init__(
        self,
        query: str,
        limit: Optional[int] = None,
        headless: bool = False,
        block_images: bool = False,
        block_media: bool = False,
        stop_event=None,
        pause_event=None,
        captcha_resume_event=None,
        captcha_hook: Optional[CaptchaHook] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.query = query
        self.limit = limit
        self.headless = headless
        self.block_images = block_images
        self.block_media = block_media
        self.stop_event = stop_event or threading.Event()
        self.pause_event = pause_event or threading.Event()
        self.captcha_resume_event = captcha_resume_event or threading.Event()
        self.captcha_hook = captcha_hook
        self._log_cb = log

    def run(self) -> Generator[Organization, None, None]:
        self._log(
            "Запускаю парсер: запрос=%s, лимит=%s, headless=%s, block_images=%s, block_media=%s",
            self.query,
            self.limit,
            self.headless,
            self.block_images,
            self.block_media,
        )
        with sync_playwright() as p:
            LOGGER.info("Запускаю браузер")
            browser = p.chromium.launch(
                headless=self.headless,
                args=[
                    "--window-size=1700,900",
                    "--disable-blink-features=AutomationControlled",
                ],
                channel="chrome",
            )
            LOGGER.info("Создаю контекст браузера")
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
            self._reset_browser_data(context)
            setup_resource_blocking(context, self.block_images, self.block_media)
            page = context.new_page()
            page.set_default_timeout(20000)

            url = f"{self.base_url}?text={quote(self.query)}"
            LOGGER.info("Открываю страницу: %s", url)
            nav_start = time.monotonic()
            page.goto(url, wait_until="domcontentloaded")
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

                self._wait_for_results(page)
                page = self._ensure_no_captcha(page)
                if page is None:
                    return

                yield from self._collect_organizations(page)
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
                LOGGER.info("Браузер закрыт")

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

    def _reset_browser_data(self, context) -> None:
        LOGGER.info("Очищаю cookies, разрешения и хранилище для новой сессии")
        try:
            context.clear_cookies()
        except Exception:
            LOGGER.warning("Failed to clear cookies")
        try:
            context.clear_permissions()
        except Exception:
            LOGGER.warning("Failed to clear permissions")
        context.add_init_script(
            """
            (() => {
              try { localStorage.clear(); } catch (e) {}
              try { sessionStorage.clear(); } catch (e) {}
              try {
                if (window.caches && caches.keys) {
                  caches.keys().then(keys => keys.forEach(key => caches.delete(key)));
                }
              } catch (e) {}
              try {
                if (window.indexedDB && indexedDB.databases) {
                  indexedDB.databases().then(dbs => {
                    dbs.forEach(db => {
                      if (db && db.name) {
                        indexedDB.deleteDatabase(db.name);
                      }
                    });
                  });
                }
              } catch (e) {}
            })();
            """
        )

    def _close_popups(self, page) -> None:
        selectors = [
            "button:has-text('Принять')",
            "button:has-text('Согласен')",
            "button:has-text('Отклонить')",
            "button:has-text('Закрыть')",
        ]
        for selector in selectors:
            try:
                LOGGER.info("Пробую закрыть всплывающее окно: %s", selector)
                click_start = time.monotonic()
                page.locator(selector).first.click(timeout=2000)
                LOGGER.info(
                    "Закрыл всплывающее окно: %s (%.2fs)",
                    selector,
                    time.monotonic() - click_start,
                )
                human_delay(0.2, 0.6)
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

    def _wait_for_results(self, page) -> None:
        LOGGER.info("Жду загрузку списка результатов")
        wait_start = time.monotonic()
        page.wait_for_selector(self.list_item_selector, timeout=30000)
        LOGGER.info(
            "Список результатов загружен за %.2fs",
            time.monotonic() - wait_start,
        )

    def _collect_organizations(self, page) -> Generator[Organization, None, None]:
        all_ids = self._collect_all_ids(page)
        total = len(all_ids)
        LOGGER.info("Уникальных организаций в списке: %s", total)
        if total == 0:
            LOGGER.info("Результаты не найдены")
            return

        self._reset_list_scroll(page)
        parsed_ids: set[str] = set()
        stalled_rounds = 0
        scroll_step = 1200

        while len(parsed_ids) < total:
            if self.stop_event.is_set():
                return
            if self.pause_event.is_set():
                while self.pause_event.is_set() and not self.stop_event.is_set():
                    time.sleep(0.1)
            page = self._ensure_no_captcha(page)
            if page is None:
                return
            if self.limit and len(parsed_ids) >= self.limit:
                LOGGER.info("Достигнут лимит: %s", self.limit)
                return

            items = page.locator(self.list_item_selector)
            count = items.count()
            if count == 0:
                LOGGER.info("Нет видимых карточек для разбора")
                break

            parsed_this_round = 0
            for index in range(count):
                if self.stop_event.is_set():
                    return
                if self.pause_event.is_set():
                    while self.pause_event.is_set() and not self.stop_event.is_set():
                        time.sleep(0.1)
                page = self._ensure_no_captcha(page)
                if page is None:
                    return
                item = items.nth(index)
                org_id = self._safe_attr(item, "data-id")
                if not org_id or org_id not in all_ids or org_id in parsed_ids:
                    continue

                if self.limit and len(parsed_ids) >= self.limit:
                    LOGGER.info("Достигнут лимит: %s", self.limit)
                    return

                if not self._click_list_item_wrapper(item, org_id):
                    continue

                card_wait_start = time.monotonic()
                card = self._wait_for_card(page, org_id)
                if not card:
                    LOGGER.info(
                        "Карточка не загрузилась (id=%s, %.2fs)",
                        org_id,
                        time.monotonic() - card_wait_start,
                    )
                    continue

                LOGGER.info(
                    "Карточка загружена (id=%s, %.2fs)",
                    org_id,
                    time.monotonic() - card_wait_start,
                )

                parse_start = time.monotonic()
                org = self._parse_card(card, org_id)
                LOGGER.info(
                    "Карточка разобрана (id=%s, %.2fs)",
                    org_id,
                    time.monotonic() - parse_start,
                )
                parsed_ids.add(org_id)
                parsed_this_round += 1
                yield org

            moved, scroll_info = self._scroll_list(page, scroll_step)
            if parsed_this_round == 0 and not moved:
                stalled_rounds += 1
            else:
                stalled_rounds = 0

            if stalled_rounds >= 1 and not moved:
                LOGGER.info("Прогресса нет и список больше не листается — завершаю")
                break

            human_delay(0.2, 0.4)

    def _collect_all_ids(self, page) -> set[str]:
        all_ids = set(self._collect_visible_ids(page))
        LOGGER.info("Собираю id карточек: старт=%s", len(all_ids))
        scroll_step = 1200
        last_scroll_move = time.monotonic()
        last_scroll_top: int | None = None
        same_scroll_top_rounds = 0

        while True:
            if self.limit and len(all_ids) >= self.limit:
                LOGGER.info("Лимит %s достигнут во время предварительной загрузки", self.limit)
                break

            moved, scroll_info = self._scroll_list(page, scroll_step)
            new_ids = self._collect_visible_ids(page)
            before_count = len(all_ids)
            all_ids.update(new_ids)
            added = len(all_ids) - before_count
            scroll_top = scroll_info.get("scrollTop") if scroll_info else None
            if added:
                LOGGER.info(
                    "После прокрутки добавлено карточек: %s (scrollTop=%s/%s)",
                    added,
                    scroll_info.get("scrollTop"),
                    scroll_info.get("maxTop"),
                )

            if scroll_top is not None:
                if last_scroll_top == scroll_top:
                    same_scroll_top_rounds += 1
                else:
                    same_scroll_top_rounds = 0
                last_scroll_top = scroll_top

            if same_scroll_top_rounds >= 3 and added == 0:
                LOGGER.info("Прокрутка уперлась в конец списка — заканчиваю предварительную загрузку")
                break

            if moved:
                last_scroll_move = time.monotonic()
                continue

            if time.monotonic() - last_scroll_move >= self.max_scroll_idle_time:
                LOGGER.info(
                    "Список не листается %.2fs — начинаю парсинг",
                    time.monotonic() - last_scroll_move,
                )
                break

            idle_start_size = len(all_ids)
            idle_start = time.monotonic()
            LOGGER.info("Дошёл до конца списка, жду новые карточки")
            while time.monotonic() - idle_start < 10:
                time.sleep(random.uniform(0.3, 0.5))
                all_ids.update(self._collect_visible_ids(page))
                if len(all_ids) > idle_start_size:
                    LOGGER.info("После ожидания загружено новых карточек: %s", len(all_ids) - idle_start_size)
                    break

            if len(all_ids) == idle_start_size:
                LOGGER.info("Новых карточек нет — заканчиваю предварительную загрузку")
                break

        return all_ids

    def _collect_visible_ids(self, page) -> list[str]:
        try:
            return page.evaluate(
                """
                (selector) => {
                  return Array.from(document.querySelectorAll(selector))
                    .map(node => node.dataset.id)
                    .filter(Boolean);
                }
                """,
                self.list_item_selector,
            )
        except Exception:
            return []

    def _safe_text(self, locator) -> str:
        try:
            if locator and locator.count() > 0:
                return sanitize_text(locator.text_content())
        except Exception:
            return ""
        return ""

    def _safe_attr(self, locator, name: str) -> str:
        try:
            if locator and locator.count() > 0:
                return sanitize_text(locator.get_attribute(name))
        except Exception:
            return ""
        return ""

    def _click_list_item_wrapper(self, item, org_id: str) -> bool:
        try:
            wrapper = item.locator(self.list_item_wrapper_selector).first
            if wrapper.count() == 0:
                LOGGER.info("Не нашёл обёртку карточки для клика (id=%s)", org_id)
                return False
            click_start = time.monotonic()
            wrapper.scroll_into_view_if_needed()
            wrapper.evaluate("el => el.click()")
            LOGGER.info("Кликнул по карточке (id=%s, %.2fs)", org_id, time.monotonic() - click_start)
            return True
        except Exception:
            LOGGER.info("Ошибка клика по карточке (id=%s)", org_id)
            return False

    def _wait_for_card(self, page, org_id: str):
        selector = f"aside.sidebar-view._shown div.business-card-view[data-id='{org_id}']"
        try:
            page.wait_for_selector(selector, timeout=2000)
            return page.locator(selector).first
        except PlaywrightTimeoutError:
            try:
                fallback = "aside.sidebar-view._shown div.business-card-view[data-id]"
                page.wait_for_selector(fallback, timeout=2000)
                return page.locator(fallback).first
            except PlaywrightTimeoutError:
                return None

    def _parse_card(self, card_root, org_id: str) -> Organization:
        title_link = card_root.locator(
            "h1.card-title-view__title a.card-title-view__title-link"
        ).first
        name = self._safe_text(title_link)
        href = self._safe_attr(title_link, "href")
        card_url = self._normalize_card_url(href, org_id)

        rating_text = self._safe_text(
            card_root.locator(".business-rating-badge-view__rating-text").first
        )
        rating = normalize_rating(rating_text)
        count_text = self._safe_text(
            card_root.locator(".business-header-rating-view__text").first
        )
        rating_count = extract_count(count_text)

        phone_text = self._safe_text(card_root.locator("span[itemprop='telephone']").first)
        phone = self._normalize_phone(phone_text)

        verified = ""
        if card_root.locator("span.business-verified-badge._prioritized").count() > 0:
            verified = "зелёная"
        elif card_root.locator("span.business-verified-badge").count() > 0:
            verified = "синяя"

        award = self._safe_text(
            card_root.locator(".business-header-awards-view__award-text").first
        )

        vk = ""
        telegram = ""
        whatsapp = ""
        links = card_root.locator("a[href]")
        for i in range(links.count()):
            href = self._safe_attr(links.nth(i), "href")
            lower_href = href.lower()
            if not vk and "vk.com" in lower_href:
                vk = href
            if not telegram and ("t.me" in lower_href or "telegram.me" in lower_href):
                telegram = href
            if not whatsapp and (
                "wa.me" in lower_href
                or "api.whatsapp.com" in lower_href
                or "whatsapp.com" in lower_href
            ):
                whatsapp = href

        website = self._extract_website(card_root)

        return Organization(
            name=name,
            phone=phone,
            verified=verified,
            award=award,
            vk=vk,
            telegram=telegram,
            whatsapp=whatsapp,
            website=website,
            card_url=card_url,
            rating=rating,
            rating_count=rating_count,
        )

    @staticmethod
    def _normalize_phone(raw_phone: str) -> str:
        digits = "".join(ch for ch in raw_phone if ch.isdigit())
        if len(digits) != 11 or digits[0] not in {"7", "8"}:
            return ""
        if digits[0] == "8":
            digits = "7" + digits[1:]
        return f"+{digits}"

    @staticmethod
    def _normalize_card_url(href: str, org_id: str) -> str:
        if org_id:
            return f"https://yandex.ru/maps/org/{org_id}/"
        if not href:
            return ""
        if href.startswith("http"):
            url = href
        elif href.startswith("//"):
            url = f"https:{href}"
        else:
            url = f"https://yandex.ru{href}"
        match = re.search(r"/maps/org/(?:[^/]+/)?(?P<org_id>\\d+)/?", url)
        if not match:
            return ""
        return f"https://yandex.ru/maps/org/{match.group('org_id')}/"

    def _extract_website(self, card_root) -> str:
        link = self._safe_attr(
            card_root.locator("a.business-urls-view__link[href]").first, "href"
        )
        if link:
            return self._normalize_website(link)
        text = self._safe_text(
            card_root.locator(".business-urls-view__text").first
        )
        return self._normalize_website(text)

    @staticmethod
    def _normalize_website(raw_url: str) -> str:
        if not raw_url:
            return ""
        url = sanitize_text(raw_url)
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("//"):
            return f"https:{url}"
        return f"https://{url}"

    def _scroll_list(self, page, step: int) -> tuple[bool, dict]:
        try:
            result = page.evaluate(
                """
                ({selector, scrollStep}) => {
                  const container = document.querySelector(selector);
                  if (!container) {
                    return { moved: false, scrollTop: 0 };
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
            time.sleep(random.uniform(0.15, 0.25))
            moved = bool(result and result.get("moved"))
            if result:
                LOGGER.info(
                    "Прокрутка списка: moved=%s, scrollTop=%s, maxTop=%s",
                    moved,
                    result.get("scrollTop"),
                    result.get("maxTop"),
                )
            return moved, (result or {})
        except Exception as exc:
            LOGGER.info("Не удалось пролистать список: %s", exc)
            return False, {}

    def _reset_list_scroll(self, page) -> None:
        try:
            page.evaluate(
                """
                (selector) => {
                  const container = document.querySelector(selector);
                  if (!container) {
                    return false;
                  }
                  container.scrollTop = 0;
                  container.dispatchEvent(new Event("scroll", { bubbles: true }));
                  return true;
                }
                """,
                self.scroll_container_selector,
            )
        except Exception:
            LOGGER.info("Не удалось сбросить прокрутку списка")
