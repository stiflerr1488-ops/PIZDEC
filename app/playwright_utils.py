from __future__ import annotations

import logging
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

