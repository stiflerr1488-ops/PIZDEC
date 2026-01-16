from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Generator, Optional
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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

    def __init__(self, query: str, limit: Optional[int] = None, headless: bool = False) -> None:
        self.query = query
        self.limit = limit
        self.headless = headless
        self.seen_links: set[str] = set()

    def run(self) -> Generator[Organization, None, None]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
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

            url = f"{self.base_url}?text={quote(self.query)}"
            LOGGER.info("Opening %s", url)
            page.goto(url, wait_until="domcontentloaded")

            self._close_popups(page)
            self._wait_for_results(page)

            yield from self._collect_organizations(page)

            context.close()
            browser.close()

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
                human_delay(0.2, 0.6)
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

    def _wait_for_results(self, page) -> None:
        page.wait_for_selector(".search-business-snippet-view", timeout=30000)

    def _collect_organizations(self, page) -> Generator[Organization, None, None]:
        no_new_rounds = 0

        while True:
            items = page.locator(".search-business-snippet-view")
            count = items.count()
            if count == 0:
                LOGGER.info("No results found")
                break

            new_added = 0
            for index in range(count):
                if self.limit and len(self.seen_links) >= self.limit:
                    return

                item = items.nth(index)
                link = self._extract_link(item)
                if not link or link in self.seen_links:
                    continue

                snippet_data = self._parse_snippet(item)
                self.seen_links.add(link)

                org = Organization(
                    name=snippet_data.get("name", ""),
                    verified=snippet_data.get("verified", ""),
                    award=snippet_data.get("award", ""),
                    card_url=snippet_data.get("card_url", ""),
                    rating=snippet_data.get("rating", ""),
                    rating_count=snippet_data.get("rating_count", ""),
                )

                LOGGER.info("Opening card: %s", org.name)
                details = self._open_and_parse_details(page, item, org.card_url)
                org.phone = details.get("phone", "")
                org.website = details.get("website", "")
                org.vk = details.get("vk", "")
                org.telegram = details.get("telegram", "")
                org.whatsapp = details.get("whatsapp", "")

                new_added += 1
                yield org

                human_delay()

            if new_added == 0:
                no_new_rounds += 1
            else:
                no_new_rounds = 0

            if self.limit and len(self.seen_links) >= self.limit:
                break

            if no_new_rounds >= 3:
                LOGGER.info("No new organizations after scrolling")
                break

            self._scroll_results(page)
            human_delay(0.8, 1.6)

    def _extract_link(self, item) -> str:
        try:
            link = item.locator("a.link-overlay[href^='/web-maps/org/']").first.get_attribute(
                "href"
            )
            return sanitize_text(link)
        except Exception:
            return ""

    def _parse_snippet(self, item) -> dict:
        name = self._safe_text(item.locator(".search-business-snippet-view__title").first)
        card_link = self._extract_link(item)
        card_url = f"https://yandex.ru{card_link}" if card_link else ""

        rating_text = self._safe_text(
            item.locator(".business-rating-badge-view__rating-text").first
        )
        rating = normalize_rating(rating_text)

        count_text = self._safe_text(item.locator(".business-rating-with-text-view__count").first)
        if not count_text:
            count_text = self._safe_text(
                item.locator(".business-rating-with-text-view .a11y-hidden").first
            )
        rating_count = extract_count(count_text)

        award = self._safe_text(item.locator(".business-header-awards-view__award-text").first)

        verified = ""
        try:
            badge = item.locator(".business-verified-badge")
            if badge.count() > 0:
                badge_class = badge.first.get_attribute("class") or ""
                if "_prioritized" in badge_class:
                    verified = "зеленая"
                else:
                    verified = "синяя"
        except Exception:
            verified = ""

        return {
            "name": name,
            "card_url": card_url,
            "rating": rating,
            "rating_count": rating_count,
            "award": award,
            "verified": verified,
        }

    def _open_and_parse_details(self, page, item, card_url: str) -> dict:
        data = self._open_details_by_click(page, item)
        if data:
            return data
        return self._open_details_by_url(page, card_url)

    def _open_details_by_click(self, page, item) -> dict:
        attempts = 0
        while attempts < 2:
            attempts += 1
            current_url = page.url
            try:
                wrapper = item.locator(
                    "xpath=ancestor::div[contains(@class, 'search-snippet-view__body-button-wrapper')]"
                ).first
                link_overlay = item.locator("a.link-overlay").first
                if wrapper.count() > 0:
                    wrapper.scroll_into_view_if_needed()
                    wrapper.click(timeout=5000)
                elif link_overlay.count() > 0:
                    link_overlay.scroll_into_view_if_needed()
                    link_overlay.click(timeout=5000)
                else:
                    item.scroll_into_view_if_needed()
                    item.click(timeout=5000)
                human_delay(0.4, 0.9)

                page.wait_for_selector(
                    "span[itemprop='telephone'], a.business-urls-view__link[itemprop='url'], "
                    "a[itemprop='sameAs']",
                    timeout=10000,
                )
                data = self._parse_details(page)
                self._return_to_results(page, current_url)
                return data
            except PlaywrightTimeoutError:
                LOGGER.warning("Timeout while opening details via click, retry %s", attempts)
                self._return_to_results(page, current_url)
            except Exception as exc:
                LOGGER.warning("Failed to parse details via click: %s", exc)
                self._return_to_results(page, current_url)

        return {}

    def _open_details_by_url(self, page, card_url: str) -> dict:
        if not card_url:
            return {
                "phone": "",
                "website": "",
                "vk": "",
                "telegram": "",
                "whatsapp": "",
            }

        attempts = 0
        while attempts < 2:
            attempts += 1
            details_page = page.context.new_page()
            details_page.set_default_timeout(20000)
            try:
                details_page.goto(card_url, wait_until="domcontentloaded")
                self._close_popups(details_page)
                details_page.wait_for_selector(
                    "span[itemprop='telephone'], a.business-urls-view__link[itemprop='url'], "
                    "a[itemprop='sameAs']",
                    timeout=10000,
                )

                return self._parse_details(details_page)
            except PlaywrightTimeoutError:
                LOGGER.warning("Timeout while opening details via url, retry %s", attempts)
            except Exception as exc:
                LOGGER.warning("Failed to parse details via url: %s", exc)
            finally:
                details_page.close()

        return {
            "phone": "",
            "website": "",
            "vk": "",
            "telegram": "",
            "whatsapp": "",
        }

    def _parse_details(self, page) -> dict:
        phone = self._safe_text(page.locator("span[itemprop='telephone']").first)

        website = self._safe_attr(
            page.locator("a.business-urls-view__link[itemprop='url']").first, "href"
        )

        vk = ""
        telegram = ""
        whatsapp = ""

        links = page.locator("a[itemprop='sameAs']")
        for i in range(links.count()):
            link = links.nth(i)
            href = self._safe_attr(link, "href")
            aria = self._safe_attr(link, "aria-label").lower()
            lower_href = href.lower()

            if ("vk.com" in lower_href or "vkontakte" in aria) and not vk:
                vk = href
            if ("t.me" in lower_href or "telegram" in aria) and not telegram:
                telegram = href
            if ("wa.me" in lower_href or "whatsapp" in aria) and not whatsapp:
                whatsapp = href

        return {
            "phone": phone,
            "website": website,
            "vk": vk,
            "telegram": telegram,
            "whatsapp": whatsapp,
        }

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

    def _return_to_results(self, page, previous_url: str) -> None:
        if page.url != previous_url and "/org/" in page.url:
            try:
                page.go_back(timeout=5000)
                human_delay(0.3, 0.6)
            except Exception:
                pass

    def _scroll_results(self, page) -> None:
        container = self._find_scroll_container(page)
        if not container:
            page.mouse.wheel(0, 1200)
            return

        try:
            page.evaluate("el => { el.scrollBy(0, el.scrollHeight); }", container)
        except Exception:
            page.mouse.wheel(0, 1200)

    def _find_scroll_container(self, page):
        selectors = [
            ".search-list-view__list",
            ".search-list-view__items",
            ".scroll__container",
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            if locator.count() > 0:
                try:
                    if locator.is_visible():
                        return locator.element_handle()
                except Exception:
                    continue
        return None
