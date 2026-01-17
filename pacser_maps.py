from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Generator, Optional
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from playwright_utils import apply_stealth, setup_resource_blocking
from utils import extract_count, human_delay, normalize_rating, sanitize_text


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

    def __init__(
        self,
        query: str,
        limit: Optional[int] = None,
        headless: bool = False,
        block_images: bool = False,
        block_media: bool = False,
        stealth: bool = True,
    ) -> None:
        self.query = query
        self.limit = limit
        self.headless = headless
        self.block_images = block_images
        self.block_media = block_media
        self.stealth = stealth

    def run(self) -> Generator[Organization, None, None]:
        LOGGER.info(
            "Запускаю парсер: запрос=%s, лимит=%s, headless=%s, block_images=%s, block_media=%s, stealth=%s",
            self.query,
            self.limit,
            self.headless,
            self.block_images,
            self.block_media,
            self.stealth,
        )
        with sync_playwright() as p:
            LOGGER.info("Запускаю браузер")
            browser = p.chromium.launch(
                headless=self.headless, args=["--window-size=1700,900"]
            )
            LOGGER.info("Создаю контекст браузера")
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1700, "height": 900},
                is_mobile=False,
                has_touch=False,
                device_scale_factor=1,
            )
            self._reset_browser_data(context)
            setup_resource_blocking(context, self.block_images, self.block_media)
            page = context.new_page()
            if self.stealth:
                apply_stealth(context, page)
            page.set_default_timeout(20000)

            url = f"{self.base_url}?text={quote(self.query)}"
            LOGGER.info("Открываю страницу: %s", url)
            page.goto(url, wait_until="domcontentloaded")

            self._close_popups(page)
            self._wait_for_results(page)

            yield from self._collect_organizations(page)

            context.close()
            browser.close()
            LOGGER.info("Браузер закрыт")

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
                page.locator(selector).first.click(timeout=2000)
                LOGGER.info("Закрыл всплывающее окно: %s", selector)
                human_delay(0.2, 0.6)
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

    def _wait_for_results(self, page) -> None:
        LOGGER.info("Жду загрузку списка результатов")
        page.wait_for_selector(self.list_item_selector, timeout=30000)
        LOGGER.info("Список результатов загружен")

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
                item = items.nth(index)
                org_id = self._safe_attr(item, "data-id")
                if not org_id or org_id not in all_ids or org_id in parsed_ids:
                    continue

                if self.limit and len(parsed_ids) >= self.limit:
                    LOGGER.info("Достигнут лимит: %s", self.limit)
                    return

                if not self._click_list_item_wrapper(item):
                    continue

                card = self._wait_for_card(page, org_id)
                if not card:
                    LOGGER.info("Карточка не загрузилась (id=%s)", org_id)
                    continue

                org = self._parse_card(card, org_id)
                parsed_ids.add(org_id)
                parsed_this_round += 1
                yield org

            moved = self._scroll_list(page, scroll_step)
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

        while True:
            if self.limit and len(all_ids) >= self.limit:
                LOGGER.info("Лимит %s достигнут во время предварительной загрузки", self.limit)
                break

            moved = self._scroll_list(page, scroll_step)
            new_ids = self._collect_visible_ids(page)
            all_ids.update(new_ids)

            if moved:
                continue

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

    def _click_list_item_wrapper(self, item) -> bool:
        try:
            wrapper = item.locator(self.list_item_wrapper_selector).first
            if wrapper.count() == 0:
                return False
            wrapper.scroll_into_view_if_needed()
            wrapper.evaluate("el => el.click()")
            return True
        except Exception:
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
            verified = "green"
        elif card_root.locator("span.business-verified-badge").count() > 0:
            verified = "blue"

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

        return Organization(
            name=name,
            phone=phone,
            verified=verified,
            award=award,
            vk=vk,
            telegram=telegram,
            whatsapp=whatsapp,
            website="",
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
        if not href:
            return ""
        if href.startswith("http"):
            url = href
        elif href.startswith("//"):
            url = f"https:{href}"
        else:
            url = f"https://yandex.ru{href}"
        if "/maps/org/" not in url:
            return ""
        if org_id and not url.endswith(f"/{org_id}/"):
            url = url.rstrip("/")
            url = f"{url.split('?')[0].rstrip('/')}/{org_id}/"
        return url

    def _scroll_list(self, page, step: int) -> bool:
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
            return bool(result and result.get("moved"))
        except Exception as exc:
            LOGGER.info("Не удалось пролистать список: %s", exc)
            return False

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
