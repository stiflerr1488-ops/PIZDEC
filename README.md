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

### CLI options

- `--query` (required): Search query like "ниша город".
- `--limit`: Limit number of organizations (default: no limit).
- `--headless`: `true` or `false` (default: false).
- `--out`: Output Excel file (default: result.xlsx).
- `--log`: Optional log file path.
