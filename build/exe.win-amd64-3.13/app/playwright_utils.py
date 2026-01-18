from __future__ import annotations

from typing import Any


CHROME_DOWNLOAD_URL = "https://chrome.browserapp.ru/"

PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
PLAYWRIGHT_VIEWPORT = {"width": 1700, "height": 900}
PLAYWRIGHT_LAUNCH_ARGS = [
    "--window-size=1700,900",
    "--disable-blink-features=AutomationControlled",
]


def is_chrome_missing_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    if "chrome" not in message:
        return False
    markers = (
        "chrome не найден",
        "chrome not found",
        "not found",
        "executable doesn't exist",
        "executable does not exist",
        "chromium distribution 'chrome' is not found",
    )
    return any(marker in message for marker in markers)


def chrome_not_found_message() -> str:
    return f"Chrome не найден. Скачайте и установите браузер: {CHROME_DOWNLOAD_URL}"


def launch_chrome(playwright: Any, *, headless: bool, args: list[str]) -> Any:
    try:
        return playwright.chromium.launch(
            headless=headless,
            args=args,
            channel="chrome",
        )
    except Exception as exc:
        if is_chrome_missing_error(exc):
            raise RuntimeError(chrome_not_found_message()) from exc
        raise

