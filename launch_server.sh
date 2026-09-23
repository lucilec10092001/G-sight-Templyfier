#!/bin/sh
set -eu
cd "$(dirname "$0")"
export TEMPLYFIER_MODE=server
: "${TEMPLYFIER_DATA_DIR:?IT configuration required. See SERVER_DEPLOYMENT.md}"
exec .venv/bin/python -m streamlit run app.py --server.headless=true
