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
        "Рейтинг",
        "Количество оценок",
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

    def _set_link_cell(self, row: int, column: int, text: str, url: str) -> None:
        if not url:
            self.sheet.cell(row=row, column=column, value="")
            return
        display_text = text or url
        cell = self.sheet.cell(row=row, column=column, value=display_text)
        cell.hyperlink = url
        cell.style = "Hyperlink"

    def append(self, organization: "Organization") -> None:
        data = asdict(organization)
        name = data.get("name", "")
        card_url = data.get("card_url", "")
        row = self.sheet.max_row + 1
        self.sheet.cell(row=row, column=1, value=name)
        if card_url:
            name_cell = self.sheet.cell(row=row, column=1)
            name_cell.hyperlink = card_url
            name_cell.style = "Hyperlink"
        self.sheet.cell(row=row, column=2, value=data.get("phone", ""))
        self.sheet.cell(row=row, column=3, value=data.get("verified", ""))
        self.sheet.cell(row=row, column=4, value=data.get("award", ""))
        self.sheet.cell(row=row, column=5, value=data.get("rating", ""))
        self.sheet.cell(row=row, column=6, value=data.get("rating_count", ""))
        self._set_link_cell(row, 7, name, data.get("vk", ""))
        self._set_link_cell(row, 8, name, data.get("telegram", ""))
        self._set_link_cell(row, 9, name, data.get("whatsapp", ""))
        self._set_link_cell(row, 10, name, data.get("website", ""))
        self._set_link_cell(row, 11, name, card_url)
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
