from __future__ import annotations

import importlib
import importlib.util
import logging
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit


LOGGER = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
MEDIA_EXTS = {".mp4", ".webm", ".avi", ".mov", ".mp3", ".wav", ".ogg", ".m4a"}


def setup_resource_blocking(context: Any, block_images: bool, block_media: bool) -> None:
    if not block_images and not block_media:
        return

    def handle_route(route, request) -> None:
        resource_type = request.resource_type
        url = request.url or ""
        path = urlsplit(url).path.lower()
        suffix = ""
        if "." in path:
            suffix = "." + path.split(".")[-1]

        is_image = resource_type == "image" or suffix in IMAGE_EXTS
        is_media = resource_type == "media" or suffix in MEDIA_EXTS

        if block_images and is_image:
            route.abort()
            return
        if block_media and is_media:
            route.abort()
            return
        route.continue_()

    context.route("**/*", handle_route)
    LOGGER.info("Блокировка ресурсов: изображения=%s, медиа=%s", block_images, block_media)


def apply_stealth(context: Any, page: Any) -> None:
    if importlib.util.find_spec("playwright_stealth") is None:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "playwright-stealth"],
                check=True,
                capture_output=True,
                text=True,
            )
            LOGGER.info("Установлен playwright-stealth для stealth-режима.")
        except Exception as exc:  # noqa: BLE001 - логируем и продолжаем с fallback.
            LOGGER.warning(
                "Не удалось установить playwright-stealth автоматически: %s. Включаю fallback.",
                exc,
            )

    if importlib.util.find_spec("playwright_stealth") is not None:
        stealth_func = None
        try:
            module = importlib.import_module("playwright_stealth")
        except Exception as exc:  # noqa: BLE001 - логируем и включаем fallback.
            LOGGER.warning(
                "Не удалось загрузить playwright_stealth: %s. Включаю fallback.",
                exc,
            )
            module = None

        if module is not None:
            for name in ("stealth_sync", "stealth", "stealth_async"):
                candidate = getattr(module, name, None)
                if callable(candidate):
                    stealth_func = candidate
                    break

        if stealth_func is not None:
            stealth_func(page)
            LOGGER.info("Включаю stealth-режим через playwright_stealth (%s)", stealth_func.__name__)
            return
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", "playwright-stealth"],
                check=True,
                capture_output=True,
                text=True,
            )
            LOGGER.info("Переустановлен playwright-stealth для совместимого stealth API.")
            module = importlib.import_module("playwright_stealth")
            for name in ("stealth_sync", "stealth", "stealth_async"):
                candidate = getattr(module, name, None)
                if callable(candidate):
                    stealth_func = candidate
                    break
            if stealth_func is not None:
                stealth_func(page)
                LOGGER.info(
                    "Включаю stealth-режим через playwright_stealth (%s)",
                    stealth_func.__name__,
                )
                return
        except Exception as exc:  # noqa: BLE001 - логируем и продолжаем с fallback.
            LOGGER.warning(
                "Не удалось переустановить playwright-stealth автоматически: %s. Включаю fallback.",
                exc,
            )
        LOGGER.warning(
            "playwright_stealth установлен, но не содержит совместимого stealth API. "
            "Ожидались функции stealth_sync/stealth/stealth_async. "
            "Проверьте, что установлен пакет playwright-stealth (pip install -U playwright-stealth). "
            "Включаю fallback."
        )

    context.add_init_script(
        """
        () => {
          Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        }
        """
    )
    LOGGER.info("Включаю stealth-режим через init_script fallback")
