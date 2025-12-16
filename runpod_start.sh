#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/workspace/fixgpt-main"
VENV_DIR="/workspace/venv"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

cd "$PROJECT_ROOT"

pip install --upgrade pip
pip install -r requirements.txt

python manage.py migrate --noinput

export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-"expandable_segments:True"}
export TRANSFORMERS_VERBOSITY=${TRANSFORMERS_VERBOSITY:-"info"}

python manage.py runserver 0.0.0.0:8000

