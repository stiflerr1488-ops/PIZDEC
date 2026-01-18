from __future__ import annotations

import sys
from pathlib import Path

from cx_Freeze import Executable, setup

BASE_DIR = Path(__file__).resolve().parent

# Folders/files placed next to the exe
include_files = [
    (str(BASE_DIR / "app"), "app"),
    (str(BASE_DIR / "config"), "config"),
    (str(BASE_DIR / "resources"), "resources"),
    (str(BASE_DIR / "ui"), "ui"),
    (str(BASE_DIR / "sysroot.json"), "sysroot.json"),
]

# Ship empty results folder (without huge/long filenames)
results_dir = BASE_DIR / "results"
results_dir.mkdir(exist_ok=True)
include_files.append((str(results_dir), "results"))

# --- Playwright extras ---
# To bundle browsers, install them into playwright package first:
#   Windows (PowerShell):  $env:PLAYWRIGHT_BROWSERS_PATH='0'; python -m playwright install chromium
#   Windows (cmd):         set PLAYWRIGHT_BROWSERS_PATH=0 && python -m playwright install chromium
# Then .local-browsers will exist and will be included below.
try:
    import playwright  # type: ignore

    pw_dir = Path(playwright.__file__).resolve().parent
    driver_dir = pw_dir / "driver"
    browsers_dir = pw_dir / ".local-browsers"

    if driver_dir.exists():
        include_files.append((str(driver_dir), "lib/playwright/driver"))
    if browsers_dir.exists():
        include_files.append((str(browsers_dir), "lib/playwright/.local-browsers"))
except Exception:
    # If playwright isn't installed at build time, the build can still proceed,
    # but the runtime will fail without playwright.
    pass

build_exe_options = {
    "include_files": include_files,
    "packages": [
        "app",
        "customtkinter",
        "playwright",
        "openpyxl",
        "qrcode",
        "PIL",
    ],
    "excludes": ["tkinter.test", "unittest"],
    "include_msvcr": True,
}

base = "gui" if sys.platform == "win32" else None

setup(
    name="PIZDEC",
    version="1.0",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "main.py",
            base=base,
            target_name="PIZDEC.exe",
        )
    ],
)
