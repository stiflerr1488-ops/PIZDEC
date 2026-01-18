#!/bin/zsh
set -e
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install cx_Freeze pillow

rm -rf build
python3 setup.py build

echo "DONE. Check build/."
