import argparse
import logging
import sys
from pathlib import Path

from yandex_maps_scraper import YandexMapsScraper
from excel_writer import ExcelWriter


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yandex Maps scraper")
    parser.add_argument("--query", help="Search query like 'ниша город'")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of organizations")
    parser.add_argument(
        "--headless",
        default="false",
        help="Run browser in headless mode (true/false)",
    )
    parser.add_argument("--out", default="result.xlsx", help="Output Excel file")
    parser.add_argument("--log", default="", help="Optional log file path")
    return parser


def setup_logging(log_path: str) -> None:
    handlers = [logging.StreamHandler()]
    if log_path:
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def prompt_query() -> str:
    niche = input("Введите нишу: ").strip()
    city = input("Введите город: ").strip()
    return f"{niche} {city}".strip()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.query:
        args.query = prompt_query()

    setup_logging(args.log)
    output_path = Path(args.out).expanduser().resolve()

    writer = ExcelWriter(output_path)
    scraper = YandexMapsScraper(
        query=args.query,
        limit=args.limit if args.limit > 0 else None,
        headless=parse_bool(args.headless),
    )

    try:
        for org in scraper.run():
            writer.append(org)
    finally:
        writer.close()


if __name__ == "__main__":
    main()
