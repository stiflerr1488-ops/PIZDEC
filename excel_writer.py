from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook


LOGGER = logging.getLogger(__name__)


class ExcelWriter:
    headers = [
        "Название",
        "Номер",
        "Галочка (синяя/зеленая/пусто)",
        "хорошее место",
        "ВК",
        "ТГ",
        "Ватсап",
        "сайт организации",
        "ссылка на карточку",
    ]

    def __init__(self, path: Path, flush_every: int = 10) -> None:
        self.path = path
        self.flush_every = flush_every
        self.workbook = Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "Organizations"
        self.sheet.append(self.headers)
        self._counter = 0
        self.flush()

    def append(self, organization: "Organization") -> None:
        data = asdict(organization)
        row = [
            data.get("name", ""),
            data.get("phone", ""),
            data.get("verified", ""),
            data.get("award", ""),
            data.get("vk", ""),
            data.get("telegram", ""),
            data.get("whatsapp", ""),
            data.get("website", ""),
            data.get("card_url", ""),
        ]
        self.sheet.append(row)
        self._counter += 1
        if self._counter % self.flush_every == 0:
            self.flush()

    def append_many(self, organizations: Iterable["Organization"]) -> None:
        for organization in organizations:
            self.append(organization)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.workbook.save(self.path)
        LOGGER.info("Saved %s", self.path)

    def close(self) -> None:
        self.flush()
        self.workbook.close()


from yandex_maps_scraper import Organization  # noqa: E402
