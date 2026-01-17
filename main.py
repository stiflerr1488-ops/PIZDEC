import argparse
import importlib.util
import logging
import os
import platform
import re
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


def parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return parse_bool(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yandex Maps scraper")
    parser.add_argument("--query", help="Search query like 'ниша в город'")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of organizations")
    parser.add_argument(
        "--headless",
        default=None,
        help="Run browser in headless mode (true/false)",
    )
    parser.add_argument(
        "--block-media",
        default=None,
        help="Block media resources for faster scraping (true/false)",
    )
    parser.add_argument(
        "--block-images",
        default=None,
        help="Block image resources for faster scraping (true/false)",
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


def _parse_requirements(requirements_path: Path) -> list[tuple[str, str]]:
    if not requirements_path.exists():
        return []
    requirements: list[tuple[str, str]] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        raw = line.split("#", 1)[0].strip()
        if not raw or raw.startswith("#"):
            continue
        requirement, marker = (part.strip() for part in raw.split(";", 1)) if ";" in raw else (raw, "")
        name = re.split(r"[<>=!~;]", requirement, maxsplit=1)[0].strip()
        name = name.split("[", 1)[0].strip()
        if name:
            requirements.append((name, marker))
    return requirements


def _parse_required_modules(requirements_path: Path) -> list[str]:
    requirements = _parse_requirements(requirements_path)
    return [
        name
        for name, marker in requirements
        if not marker or _marker_allows_install(marker)
    ]


def _find_incompatible_requirements(requirements_path: Path) -> dict[str, str]:
    requirements = _parse_requirements(requirements_path)
    return {
        name: marker
        for name, marker in requirements
        if marker and not _marker_allows_install(marker)
    }


def _marker_allows_install(marker: str) -> bool:
    if not marker:
        return True
    try:
        from packaging.markers import Marker

        return Marker(marker).evaluate()
    except Exception:
        pass
    marker = marker.strip()
    if " or " in marker:
        return any(_marker_allows_install(part) for part in marker.split(" or "))
    if " and " in marker:
        return all(_marker_allows_install(part) for part in marker.split(" and "))
    match = re.match(r"python_version\s*([<>=!]=?|==)\s*['\"]([^'\"]+)['\"]", marker)
    if not match:
        return True
    op, version = match.groups()
    current = _version_tuple(f"{sys.version_info.major}.{sys.version_info.minor}")
    target = _version_tuple(version)
    return _compare_versions(current, target, op)


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def _compare_versions(left: tuple[int, ...], right: tuple[int, ...], op: str) -> bool:
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    return True


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


def ensure_dependencies(require_gui: bool) -> None:
    incompatible = _find_incompatible_requirements(REQUIREMENTS_FILE)
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if require_gui and "kivy" in incompatible:
        raise RuntimeError(
            "GUI режим требует библиотеку Kivy, которая недоступна для "
            f"Python {py_version} ({incompatible['kivy']}). "
            "Установите Python 3.12 или ниже, либо запустите программу с флагом --cli."
        )
    if not require_gui and "playwright" in incompatible:
        raise RuntimeError(
            "CLI режим требует Playwright, который недоступен для "
            f"Python {py_version} ({incompatible['playwright']}). "
            "Установите Python 3.13 или ниже."
        )
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


def ensure_gui_dependencies() -> None:
    if importlib.util.find_spec("kivy") is not None:
        return
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    raise RuntimeError(
        "GUI режим требует библиотеку Kivy. "
        f"Для Python {py_version} она может быть недоступна. "
        "Установите Python 3.12 или ниже, либо запустите программу с флагом --cli."
    )


def run_cli(args: argparse.Namespace) -> None:
    from excel_writer import ExcelWriter
    from filters import passes_potential_filters
    from notifications import notify_sound
    from parser_search import run_fast_parser
    from settings_store import load_settings
    from utils import build_result_paths, configure_logging, split_query
    from pacser_maps import YandexMapsScraper

    if not args.query:
        args.query = prompt_query()

    settings = load_settings()
    niche, city = split_query(args.query)
    full_path, potential_path, results_folder = build_result_paths(
        niche=niche,
        city=city,
        results_dir=RESULTS_DIR,
    )
    configure_logging(
        settings.program.log_level,
        Path(args.log) if args.log else None,
        results_folder / "log.txt",
    )
    headless_override = parse_optional_bool(args.headless)
    if headless_override is not None:
        settings.program.headless = headless_override
    block_images_override = parse_optional_bool(args.block_images)
    if block_images_override is not None:
        settings.program.block_images = block_images_override
    block_media_override = parse_optional_bool(args.block_media)
    if block_media_override is not None:
        settings.program.block_media = block_media_override

    if args.mode == "fast":
        stop_event = threading.Event()
        pause_event = threading.Event()
        captcha_event = threading.Event()
        count = run_fast_parser(
            query=args.query,
            full_output_path=full_path,
            potential_output_path=potential_path,
            lr="120590",
            max_clicks=800,
            delay_min_s=0.05,
            delay_max_s=0.15,
            stop_event=stop_event,
            pause_event=pause_event,
            captcha_resume_event=captcha_event,
            log=logging.info,
            settings=settings,
        )
        if settings.program.open_result:
            open_file(results_folder)
        notify_sound("finish", settings)
        return

    writer = ExcelWriter(full_path, potential_path)
    stop_event = threading.Event()
    pause_event = threading.Event()
    captcha_event = threading.Event()

    def _captcha_hook(stage: str, _page: object) -> None:
        if stage == "detected":
            notify_sound("captcha", settings)

    scraper = YandexMapsScraper(
        query=args.query,
        limit=args.limit if args.limit > 0 else None,
        headless=settings.program.headless,
        block_images=settings.program.block_images,
        block_media=settings.program.block_media,
        stop_event=stop_event,
        pause_event=pause_event,
        captcha_resume_event=captcha_event,
        captcha_hook=_captcha_hook,
        log=logging.info,
    )

    try:
        for org in scraper.run():
            include = passes_potential_filters(org, settings)
            writer.append(org, include_in_potential=include)
    finally:
        writer.close()
        if settings.program.open_result:
            open_file(results_folder)
        notify_sound("finish", settings)


def run_gui() -> None:
    from gui import main as gui_main

    gui_main()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    ensure_dependencies(require_gui=not args.cli)
    if args.cli:
        run_cli(args)
    else:
        ensure_gui_dependencies()
        run_gui()


if __name__ == "__main__":
    main()
