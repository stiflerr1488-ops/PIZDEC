import argparse
import logging
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path

from fast_parser import run_fast_parser
from yandex_maps_scraper import YandexMapsScraper
from excel_writer import ExcelWriter


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yandex Maps scraper")
    parser.add_argument("--query", help="Search query like 'ниша в город'")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of organizations")
    parser.add_argument(
        "--headless",
        default="false",
        help="Run browser in headless mode (true/false)",
    )
    parser.add_argument(
        "--block-media",
        default="false",
        help="Block image and media resources for faster scraping (true/false)",
    )
    parser.add_argument(
        "--mode",
        default="slow",
        choices=["slow", "fast"],
        help="Parser mode: slow (maps scraper) or fast (search parser)",
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


def open_file(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return
        if platform.system() == "Darwin":
            subprocess.run(["open", str(path)], check=False)
            return
        subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        logging.exception("Не удалось открыть файл %s", path)


def prompt_query() -> str:
    niche = input("Введите нишу: ").strip()
    city = input("Введите город: ").strip()
    return f"{niche} в {city}".strip()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.query:
        args.query = prompt_query()

    setup_logging(args.log)
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "results"
    output_name = Path(args.out).name
    output_path = output_dir / output_name

    if args.mode == "fast":
        stop_event = threading.Event()
        pause_event = threading.Event()
        captcha_event = threading.Event()
        run_fast_parser(
            query=args.query,
            output_path=output_path,
            lr="120590",
            max_clicks=800,
            delay_min_s=0.05,
            delay_max_s=0.15,
            stop_event=stop_event,
            pause_event=pause_event,
            captcha_resume_event=captcha_event,
            log=logging.info,
        )
        open_file(output_path)
        return

    writer = ExcelWriter(output_path)
    scraper = YandexMapsScraper(
        query=args.query,
        limit=args.limit if args.limit > 0 else None,
        headless=parse_bool(args.headless),
        block_media=parse_bool(args.block_media),
    )

    try:
        for org in scraper.run():
            writer.append(org)
    finally:
        writer.close()
        open_file(output_path)


if __name__ == "__main__":
    main()
