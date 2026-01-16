from __future__ import annotations

import logging
import time
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
        self._scroll_until_no_new(page, idle_timeout=10)

        items = page.locator(".search-business-snippet-view")
        count = items.count()
        LOGGER.info("Found %s result cards on page", count)
        if count == 0:
            LOGGER.info("No results found")
            return

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
            details = self._open_and_parse_details(page, item, org.card_url)
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

            yield org

            human_delay()

    def _scroll_until_no_new(self, page, idle_timeout: float = 10) -> None:
        items = page.locator(".search-business-snippet-view")
        last_count = items.count()
        last_new = time.monotonic()
        LOGGER.info("Preloading cards: starting with %s items", last_count)

        while True:
            if self.limit and last_count >= self.limit:
                LOGGER.info("Limit %s reached during preload", self.limit)
                break

            self._scroll_results(page)
            human_delay(0.6, 1.2)

            current_count = items.count()
            if current_count > last_count:
                LOGGER.info("Loaded %s new cards", current_count - last_count)
                last_count = current_count
                last_new = time.monotonic()
                continue

            if time.monotonic() - last_new >= idle_timeout:
                LOGGER.info("No new cards for %s seconds, starting parse", idle_timeout)
                break

            human_delay(0.3, 0.6)

    def _extract_link(self, item) -> str:
        selectors = [
            "a.link-overlay[href*='/org/']",
            "a[href*='/org/']",
        ]
        for selector in selectors:
            try:
                locator = item.locator(selector).first
                if locator.count() == 0:
                    continue
                link = locator.get_attribute("href") or locator.get_attribute("data-href") or ""
                link = sanitize_text(link)
                if link:
                    return link
            except Exception:
                continue
        return ""

    def _parse_snippet(self, item) -> dict:
        name = self._safe_text(item.locator(".search-business-snippet-view__title").first)
        card_link = self._extract_link(item)
        card_url = ""
        if card_link:
            if card_link.startswith("http"):
                card_url = card_link
            elif card_link.startswith("//"):
                card_url = f"https:{card_link}"
            else:
                card_url = f"https://yandex.ru{card_link}"

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
        LOGGER.info("Opening details via click")
        return self._open_details_by_click(page, item)

    def _open_details_by_click(self, page, item) -> dict:
        attempts = 0
        while attempts < 2:
            attempts += 1
            current_url = page.url
            try:
                LOGGER.info("Click open attempt %s", attempts)
                if not self._click_card_safe(page, item):
                    link_overlay = item.locator("a.link-overlay[href*='/org/']").first
                    title_link = item.locator(
                        "a.search-business-snippet-view__title[href*='/org/']"
                    ).first
                    if link_overlay.count() > 0:
                        LOGGER.info("Clicking link overlay")
                        link_overlay.scroll_into_view_if_needed()
                        link_overlay.click(timeout=5000)
                    elif title_link.count() > 0:
                        LOGGER.info("Clicking title link")
                        title_link.scroll_into_view_if_needed()
                        title_link.click(timeout=5000)
                    else:
                        LOGGER.info("No safe click target, skipping card")
                        return {}
                human_delay(0.4, 0.9)

                page.wait_for_selector(
                    "span[itemprop='telephone'], a[href^='tel:'], "
                    "a.business-urls-view__link[itemprop='url'], a.orgpage-urls-view__link, "
                    "a[itemprop='sameAs']",
                    timeout=10000,
                )
                LOGGER.info("Details loaded after click")
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

    def _click_card_safe(self, page, item) -> bool:
        item.scroll_into_view_if_needed()
        box = item.bounding_box()
        if not box:
            LOGGER.info("Card bounding box not found")
            return False

        excluded_selectors = [
            ".search-business-snippet-view__photo",
            ".search-business-snippet-view__gallery",
            ".search-business-snippet-view__reviews",
            ".search-business-snippet-view__actions",
            ".business-review-view",
            ".business-photos-view",
            "button",
            "a",
        ]
        excluded_boxes = []
        for selector in excluded_selectors:
            locator = item.locator(selector)
            for i in range(locator.count()):
                child_box = locator.nth(i).bounding_box()
                if child_box:
                    excluded_boxes.append(child_box)

        candidates = [
            (box["x"] + 8, box["y"] + 8),
            (box["x"] + box["width"] / 2, box["y"] + 8),
            (box["x"] + 8, box["y"] + box["height"] / 2),
            (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2),
            (box["x"] + box["width"] - 8, box["y"] + box["height"] - 8),
        ]

        for x, y in candidates:
            if self._point_in_any_box(x, y, excluded_boxes):
                continue
            LOGGER.info("Clicking card container at x=%.1f y=%.1f", x, y)
            page.mouse.click(x, y)
            return True

        LOGGER.info("No safe click point inside card container")
        return False

    @staticmethod
    def _point_in_any_box(x: float, y: float, boxes: list[dict]) -> bool:
        for box in boxes:
            if (
                box["x"] <= x <= box["x"] + box["width"]
                and box["y"] <= y <= box["y"] + box["height"]
            ):
                return True
        return False

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
                LOGGER.info("URL open attempt %s: %s", attempts, card_url)
                details_page.goto(card_url, wait_until="domcontentloaded")
                self._close_popups(details_page)
                details_page.wait_for_selector(
                    "span[itemprop='telephone'], a[href^='tel:'], "
                    "a.business-urls-view__link[itemprop='url'], a.orgpage-urls-view__link, "
                    "a[itemprop='sameAs']",
                    timeout=10000,
                )
                LOGGER.info("Details loaded from url")
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
        if not phone:
            phone = self._safe_attr(page.locator("a[href^='tel:']").first, "href").replace(
                "tel:", ""
            )

        website = self._safe_attr(
            page.locator("a.business-urls-view__link[itemprop='url']").first, "href"
        )
        if not website:
            website = self._safe_attr(page.locator("a.orgpage-urls-view__link").first, "href")

        vk = ""
        telegram = ""
        whatsapp = ""

        links = page.locator("a[itemprop='sameAs']")
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
            thumb = page.locator(".scroll__scrollbar-thumb").first
            if thumb.count() > 0:
                try:
                    LOGGER.info("Dragging scrollbar thumb")
                    track = page.locator(".scroll__scrollbar-track").first
                    thumb_box = thumb.bounding_box()
                    track_box = track.bounding_box() if track.count() > 0 else None
                    if thumb_box:
                        start_x = thumb_box["x"] + thumb_box["width"] / 2
                        start_y = thumb_box["y"] + thumb_box["height"] / 2
                        if track_box:
                            target_y = (
                                track_box["y"]
                                + track_box["height"]
                                - thumb_box["height"] / 2
                            )
                        else:
                            target_y = start_y + thumb_box["height"] * 4
                        page.mouse.move(start_x, start_y)
                        page.mouse.down()
                        page.mouse.move(start_x, target_y)
                        page.mouse.up()
                        return
                except Exception:
                    LOGGER.info("Failed to drag scrollbar thumb")

            LOGGER.info("Scroll container not found, using mouse wheel")
            page.mouse.wheel(0, 1200)
            return

        try:
            LOGGER.info("Scrolling container")
            container.scroll_into_view_if_needed()
            container.hover()
            page.evaluate(
                "el => { el.scrollTop = el.scrollHeight; }",
                container,
            )
            page.mouse.wheel(0, 1200)
        except Exception:
            LOGGER.info("Failed to scroll container, using mouse wheel")
            page.mouse.wheel(0, 1200)

    def _find_scroll_container(self, page):
        selectors = [
            ".search-list-view__list",
            ".search-list-view__items",
            ".search-list-view__scrollbar",
            ".search-list-view__content",
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
