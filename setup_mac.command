#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "== PIZDEC mac setup =="

# 1) Xcode Command Line Tools
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Installing Xcode Command Line Tools..."
  xcode-select --install || true
  echo "After CLT install finishes, re-run this script."
  read -n 1 -s -r
  exit 0
fi

# 2) Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # add brew to PATH for current session
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
else
  # ensure brew in PATH for current session
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

# 3) Python 3
if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing Python 3..."
  brew install python
fi

# 4) venv + deps
echo "Creating venv..."
python3 -m venv .venv
source .venv/bin/activate

echo "Upgrading pip..."
python3 -m pip install -U pip setuptools wheel

echo "Installing project requirements..."
if [ -f requirements.txt ]; then
  python3 -m pip install -r requirements.txt
fi

echo "Installing build deps..."
python3 -m pip install cx_Freeze pillow

# 5) Playwright + Chrome requirement
echo "Installing Playwright..."
python3 -m pip install playwright

echo "NOTE: Your app uses Playwright channel='chrome'."
echo "Make sure Google Chrome is installed on this Mac:"
echo "  /Applications/Google Chrome.app"
if [ ! -d "/Applications/Google Chrome.app" ]; then
  echo "Chrome NOT found. Install Google Chrome, then re-run if needed."
fi

# 6) Optional: build right away
echo "Building cx_Freeze app..."
rm -rf build
python3 setup.py build

echo ""
echo "DONE."
echo "Build output is in: build/"
read -n 1 -s -r
