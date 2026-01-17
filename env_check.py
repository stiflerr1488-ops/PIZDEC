from __future__ import annotations
import sys
import importlib
from typing import List, Tuple

def _ok_line(label: str) -> str:
    return f"✅ {label}"

def _bad_line(label: str) -> str:
    return f"❌ {label}"

def run_checks() -> Tuple[bool, List[str]]:
    lines: List[str] = []
    ok = True

    lines.append("🧩 Проверка окружения...")

    py = sys.version_info
    # NOTE: 3.14.2 looks like a placeholder and will fail for most users.
    # Playwright + customtkinter work well on Python 3.10+.
    want = (3, 10, 0)
    if (py.major, py.minor, py.micro) >= want:
        lines.append(_ok_line(f"Python {py.major}.{py.minor}.{py.micro}"))
    else:
        ok = False
        lines.append(_bad_line(f"Python {py.major}.{py.minor}.{py.micro} (нужно >= 3.10)"))

    # Список библиотек для проверки
    libs_to_check = [
        ("customtkinter", "customtkinter"),
        ("pandas", "pandas"),
        ("playwright", "playwright"),
        ("PIL", "pillow"),
        ("playwright_stealth", "playwright-stealth"),  # <-- Добавлено
    ]

    for mod, label in libs_to_check:
        try:
            importlib.import_module(mod)
            lines.append(_ok_line(label))
        except Exception:
            # Для stealth делаем исключение: если его нет, программа работать БУДЕТ,
            # но без защиты. Поэтому не ставим ok = False, просто пишем предупреждение.
            if mod == "playwright_stealth":
                lines.append(f"⚠️ {label} (не установлен, защита будет слабее)")
                lines.append("   👉 pip install playwright-stealth")
            else:
                ok = False
                lines.append(_bad_line(f"{label} (не установлен)"))

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        lines.append(_ok_line("Playwright Chromium готов."))
    except Exception as e:
        ok = False
        msg = str(e).strip().splitlines()[0] if str(e).strip() else "ошибка"
        lines.append(_bad_line(f"Playwright Chromium не готов: {msg}"))
        lines.append("ℹ️ Попробуй: python -m playwright install chromium")

    if ok:
        lines.append(_ok_line("Всё готово. Запуск GUI..."))
    else:
        lines.append("⚠️ Не всё готово. GUI запустится, но парсер может не работать.")

    return ok, lines
