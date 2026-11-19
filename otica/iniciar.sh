#!/bin/sh
# Mac/Linux: ./iniciar.sh
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3 não encontrado. Instale em python.org"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python app.py
