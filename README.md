# Yandex Maps Scraper

Инструмент для парсинга организаций в Яндексе: «подробный» (Карты) и «быстрый» (поиск).

## Setup

```bash
pip install -r requirements.txt
playwright install
```

## Usage

```bash
python main.py --query "английский пушкин" --out result.xlsx --headless false
```

Если `--query` не передан, программа запросит нишу и город через консоль.

## GUI

```bash
python gui.py
```

GUI позволяет выбирать между «подробный» (скрапер по картам) и «быстрый» (парсинг поиска) режимами.

### CLI options

- `--query`: Search query like "ниша город". If omitted, the program will ask for niche and city.
- `--limit`: Limit number of organizations (default: no limit).
- `--headless`: `true` or `false` (default: false).
- `--mode`: `slow` (Карты) или `fast` (Поиск).
- `--out`: Output Excel file (default: result.xlsx).
- `--log`: Optional log file path.
