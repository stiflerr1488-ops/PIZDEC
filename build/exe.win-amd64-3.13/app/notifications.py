from __future__ import annotations

import logging
import os

from app.settings_model import Settings


LOGGER = logging.getLogger(__name__)


def notify_sound(event: str, settings: Settings) -> None:
    event = (event or "").lower()
    enabled = False
    if event == "finish":
        enabled = settings.notifications.on_finish
    elif event == "captcha":
        enabled = settings.notifications.on_captcha
    elif event == "error":
        enabled = settings.notifications.on_error
    elif event == "autosave":
        enabled = settings.notifications.on_autosave

    if not enabled:
        return

    if os.name == "nt":
        import winsound

        try:
            winsound.MessageBeep()
        except Exception:
            try:
                winsound.Beep(750, 200)
            except Exception:
                LOGGER.debug("Failed to play Windows beep")
    else:
        print("\a", end="", flush=True)
    LOGGER.info("Звук уведомления: %s", event)
