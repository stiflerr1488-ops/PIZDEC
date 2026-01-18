from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook

from app.reviews_parser import Review


LOGGER = logging.getLogger(__name__)


class ReviewsExcelWriter:
    headers = [
        "Имя пользователя",
        "Оценка",
        "Дата отзыва",
        "Полный текст отзыва",
        "Дата ответа организации",
        "Текст ответа организации",
    ]

    def __init__(self, path: Path, flush_every: int = 10) -> None:
        self.path = path
        self.flush_every = flush_every
        self.workbook = Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "REVIEWS"
        self.sheet.append(self.headers)
        self._counter = 0
        self.flush()

    def append(self, review: Review) -> None:
        data = asdict(review)
        row = self.sheet.max_row + 1
        name_cell = self.sheet.cell(row=row, column=1, value=data.get("user_name", ""))
        profile_url = data.get("user_profile_url", "")
        if profile_url:
            name_cell.hyperlink = profile_url
            name_cell.style = "Hyperlink"
        self.sheet.cell(row=row, column=2, value=data.get("rating", ""))
        self.sheet.cell(row=row, column=3, value=data.get("review_date", ""))
        self.sheet.cell(row=row, column=4, value=data.get("review_text", ""))
        self.sheet.cell(row=row, column=5, value=data.get("response_date", ""))
        self.sheet.cell(row=row, column=6, value=data.get("response_text", ""))
        self._counter += 1
        if self._counter % self.flush_every == 0:
            self.flush()

    def append_many(self, reviews: Iterable[Review]) -> None:
        for review in reviews:
            self.append(review)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.workbook.save(self.path)
        LOGGER.info("Сохранил файл: %s", self.path)

    def close(self) -> None:
        self.flush()
        self.workbook.close()
