# Yandex Maps Scraper

CLI tool to scrape organizations from Yandex Maps search results.

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

### CLI options

- `--query`: Search query like "ниша город". If omitted, the program will ask for niche and city.
- `--limit`: Limit number of organizations (default: no limit).
- `--headless`: `true` or `false` (default: false).
- `--out`: Output Excel file (default: result.xlsx).
- `--log`: Optional log file path.
