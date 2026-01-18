import sys
from cx_Freeze import setup, Executable

APP_NAME = "PIZDEC"
APP_VERSION = "1.0.0"
MAIN_SCRIPT = "main.py"
ICON_ICO = "resources/icon.ico"

base = "gui" if sys.platform == "win32" else None

build_exe_options = {
    "include_files": [
        ("app", "app"),
        ("config", "config"),
        ("resources", "resources"),
        ("ui", "ui"),
        ("sysroot.json", "sysroot.json"),
        ("results", "results"),
    ],
}

executables = [
    Executable(
        MAIN_SCRIPT,
        base=base,
        target_name=f"{APP_NAME}.exe",
        icon=ICON_ICO,
    )
]

setup(
    name=APP_NAME,
    version=APP_VERSION,
    description=APP_NAME,
    options={
        "build_exe": build_exe_options,
    },
    executables=executables,
)
