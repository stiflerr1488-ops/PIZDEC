import argparse
import importlib.util
import logging
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "results"
REQUIREMENTS_FILE = SCRIPT_DIR / "requirements.txt"
PLAYWRIGHT_MARKER = SCRIPT_DIR / ".playwright_installed"


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
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in CLI mode instead of GUI",
    )
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


def _parse_required_modules(requirements_path: Path) -> list[str]:
    if not requirements_path.exists():
        return []
    modules: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        name = raw.split("==", 1)[0].strip()
        if name:
            modules.append(name)
    return modules


def _missing_modules(modules: list[str]) -> list[str]:
    missing: list[str] = []
    for module in modules:
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    return missing


def _install_requirements(requirements_path: Path) -> None:
    print("⬇️  Устанавливаю зависимости...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
        check=True,
    )


def _ensure_playwright_browser_installed() -> None:
    if PLAYWRIGHT_MARKER.exists():
        return
    print("🎭 Устанавливаю браузер Playwright (chromium)...", flush=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    PLAYWRIGHT_MARKER.write_text("ok", encoding="utf-8")


def ensure_dependencies() -> None:
    modules = _parse_required_modules(REQUIREMENTS_FILE)
    if not modules:
        return
    missing = _missing_modules(modules)
    if missing:
        print(f"📦 Не найдены зависимости: {', '.join(missing)}", flush=True)
        _install_requirements(REQUIREMENTS_FILE)
    remaining = _missing_modules(modules)
    if remaining:
        raise RuntimeError(f"Не удалось установить зависимости: {', '.join(remaining)}")
    if "playwright" in modules:
        _ensure_playwright_browser_installed()


def run_cli(args: argparse.Namespace) -> None:
    from excel_writer import ExcelWriter
    from parser_search import run_fast_parser
    from yandex_maps_scraper import YandexMapsScraper

    if not args.query:
        args.query = prompt_query()

    setup_logging(args.log)
    output_name = Path(args.out).name
    output_path = RESULTS_DIR / output_name

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


def run_gui() -> None:
    from gui import main as gui_main

    gui_main()


def main() -> None:
    ensure_dependencies()
    parser = build_parser()
    args = parser.parse_args()
    if args.cli:
        run_cli(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()
