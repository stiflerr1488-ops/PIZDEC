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
        LOGGER.info(
            "Starting scraper: query=%s limit=%s headless=%s",
            self.query,
            self.limit,
            self.headless,
        )
        with sync_playwright() as p:
            LOGGER.info("Launching browser")
            browser = p.chromium.launch(headless=self.headless)
            LOGGER.info("Creating browser context")
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
            LOGGER.info("Browser closed")

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
                LOGGER.info("Closed popup via selector: %s", selector)
                human_delay(0.2, 0.6)
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

    def _wait_for_results(self, page) -> None:
        LOGGER.info("Waiting for search results list")
        page.wait_for_selector(".search-business-snippet-view", timeout=30000)
        LOGGER.info("Search results list is visible")

    def _collect_organizations(self, page) -> Generator[Organization, None, None]:
        no_new_rounds = 0

        while True:
            items = page.locator(".search-business-snippet-view")
            count = items.count()
            LOGGER.info("Found %s result cards on page", count)
            if count == 0:
                LOGGER.info("No results found")
                break

            new_added = 0
            for index in range(count):
                if self.limit and len(self.seen_links) >= self.limit:
                    LOGGER.info("Reached limit %s", self.limit)
                    return

                item = items.nth(index)
                link = self._extract_link(item)
                if not link or link in self.seen_links:
                    if not link:
                        LOGGER.info("Skipping result %s: empty link", index)
                    else:
                        LOGGER.info("Skipping result %s: already processed", index)
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

                LOGGER.info("Opening card: %s (%s)", org.name, org.card_url)
                details = self._open_and_parse_details(page, item, org.name, org.card_url)
                org.phone = details.get("phone", "")
                org.website = details.get("website", "")
                org.vk = details.get("vk", "")
                org.telegram = details.get("telegram", "")
                org.whatsapp = details.get("whatsapp", "")
                LOGGER.info(
                    "Parsed details: phone=%s website=%s vk=%s telegram=%s whatsapp=%s",
                    org.phone,
                    org.website,
                    org.vk,
                    org.telegram,
                    org.whatsapp,
                )

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

            LOGGER.info("Scrolling results list")
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

    def _open_and_parse_details(self, page, item, name: str, card_url: str) -> dict:
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                LOGGER.info("Opening details attempt %s", attempts)
                self._open_card_from_item(page, item, card_url)
                self._wait_for_card_details(page, name)
                details_root = self._get_details_root(page)
                return self._parse_details(details_root)
            except PlaywrightTimeoutError:
                LOGGER.warning("Timeout while opening details, retry %s", attempts)
            except Exception as exc:
                LOGGER.warning("Failed to parse details: %s", exc)

        return {
            "phone": "",
            "website": "",
            "vk": "",
            "telegram": "",
            "whatsapp": "",
        }

    def _open_card_from_item(self, page, item, card_url: str) -> None:
        click_targets = [
            ".search-snippet-view__body-button-wrapper",
            "a.link-overlay[href^='/web-maps/org/']",
            ".search-business-snippet-view__content",
        ]

        for selector in click_targets:
            locator = item.locator(selector).first
            if locator.count() == 0:
                LOGGER.info("Click target not found: %s", selector)
                continue
            try:
                locator.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            try:
                LOGGER.info("Clicking selector: %s", selector)
                locator.click(timeout=3000)
                human_delay(0.2, 0.5)
                LOGGER.info("Clicked selector: %s", selector)
                return
            except Exception:
                LOGGER.info("Failed to click selector: %s", selector)
                continue

        if card_url:
            LOGGER.info("Falling back to direct navigation: %s", card_url)
            page.goto(card_url, wait_until="domcontentloaded")

    def _wait_for_card_details(self, page, name: str) -> None:
        selectors = [
            ".search-business-card-view",
            ".business-card-view",
            ".sidebar-content-view",
        ]
        LOGGER.info("Waiting for card details")
        page.wait_for_selector(", ".join(selectors), timeout=10000)
        for selector in selectors:
            try:
                card = page.locator(selector).first
                if card.count() == 0:
                    continue
                if name:
                    title = card.locator(
                        ".search-business-card-view__title, .business-card-view__title",
                        has_text=name,
                    ).first
                    if title.count() > 0:
                        title.wait_for(state="visible", timeout=2000)
                break
            except Exception:
                continue
        LOGGER.info("Card details are visible")

    def _get_details_root(self, page):
        selectors = [
            ".search-business-card-view",
            ".business-card-view",
            ".sidebar-content-view",
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator
        return page

    def _parse_details(self, root) -> dict:
        phone = self._safe_text(root.locator("span[itemprop='telephone']").first)

        website = self._safe_attr(
            root.locator("a.business-urls-view__link[itemprop='url']").first, "href"
        )

        vk = ""
        telegram = ""
        whatsapp = ""

        links = root.locator("a[itemprop='sameAs']")
        LOGGER.info("Parsing %s social links", links.count())
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
            LOGGER.info("Scroll container not found, using mouse wheel")
            page.mouse.wheel(0, 1200)
            return

        try:
            LOGGER.info("Scrolling container")
            page.evaluate("el => { el.scrollBy(0, el.scrollHeight); }", container)
        except Exception:
            LOGGER.info("Failed to scroll container, using mouse wheel")
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
                        LOGGER.info("Scroll container found: %s", selector)
                        return locator.element_handle()
                except Exception:
                    continue
        return None
