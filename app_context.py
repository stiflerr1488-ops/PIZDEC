from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
RESULTS_DIR = BASE_DIR / "results"

# Minimal shared UI state (kept simple)
UI_ROOT = None
