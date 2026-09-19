#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONDA_ENV="/home/xern/miniconda3/envs/reel_fact_checker"
PYTHON="$CONDA_ENV/bin/python"
UVICORN="$CONDA_ENV/bin/uvicorn"

echo "======================================================="
echo " Starting ReelFact: AI Instagram Reel Fact-Checker"
echo " Environment: $CONDA_ENV"
echo " Host: http://localhost:8000"
echo "======================================================="

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
exec "$UVICORN" app.api.main:app --host 0.0.0.0 --port 8000 --reload
