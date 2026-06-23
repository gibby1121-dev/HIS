#!/usr/bin/env bash
#
# run_market_snapshot.sh
# ----------------------
# Executive one-shot driver for the Sandhills Market Snapshot pipeline.
#
# It validates the environment and inputs, runs market_snapshot.py with live
# status output, and confirms the NotebookLM-ready document was produced.
# Any file-format / environment problem stops the run with a loud, specific
# alert and a non-zero exit code.
#
# Usage:   ./run_market_snapshot.sh
#
set -euo pipefail

# Resolve the directory this script lives in so it can be run from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PY_SCRIPT="market_snapshot.py"
OUTPUT="notebooklm_source.md"
REQUIRED_INPUTS=("inventory.csv" "webstats.csv" "market_trends.csv")

# ---- pretty printing -------------------------------------------------------
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow(){ printf '\033[33m%s\033[0m\n' "$*"; }

abort() {
    red "‼ ABORTING: $*"
    red "  The market snapshot was NOT generated. Please fix the issue above and re-run."
    exit 1
}

echo
bold "######################################################################"
bold "#  SANDHILLS MARKET SNAPSHOT  —  executive pipeline runner            #"
bold "######################################################################"
echo
yellow ">> Working directory: $SCRIPT_DIR"
echo

# ---- 1. locate a Python interpreter ---------------------------------------
yellow ">> [1/4] Checking for Python ..."
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    abort "Python is not installed or not on PATH. Install Python 3.8+ and retry."
fi
green "   Found: $($PY --version 2>&1)"

# ---- 2. confirm pandas is importable --------------------------------------
yellow ">> [2/4] Checking for required Python package 'pandas' ..."
if ! $PY -c "import pandas" >/dev/null 2>&1; then
    yellow "   pandas not found — attempting 'pip install pandas' ..."
    if ! $PY -m pip install pandas; then
        abort "Could not install pandas automatically. Run '$PY -m pip install pandas' manually."
    fi
fi
green "   pandas is available."

# ---- 3. verify every input file exists and is non-empty -------------------
yellow ">> [3/4] Validating input files ..."
[ -f "$PY_SCRIPT" ] || abort "Pipeline script '$PY_SCRIPT' is missing from $SCRIPT_DIR."
for f in "${REQUIRED_INPUTS[@]}"; do
    if [ ! -f "$f" ]; then
        abort "Required input '$f' was not found. (Did a source export get renamed or moved?)"
    fi
    if [ ! -s "$f" ]; then
        abort "Required input '$f' is empty. (A source export may have failed.)"
    fi
    green "   OK  $f ($(wc -l < "$f" | tr -d ' ') lines)"
done

# ---- 4. run the pipeline ---------------------------------------------------
echo
yellow ">> [4/4] Running pipeline — watch the live data validation below ..."
echo "----------------------------------------------------------------------"
if ! $PY "$PY_SCRIPT"; then
    echo "----------------------------------------------------------------------"
    abort "The Python pipeline reported an error (see messages above). \
This usually means a source file's columns or format changed."
fi
echo "----------------------------------------------------------------------"

# ---- confirm the deliverable ----------------------------------------------
if [ ! -s "$OUTPUT" ]; then
    abort "Pipeline finished but '$OUTPUT' is missing or empty."
fi

echo
green "######################################################################"
green "#  SUCCESS                                                            #"
green "######################################################################"
bold  "  Deliverable: $SCRIPT_DIR/$OUTPUT"
echo  "  Size: $(wc -c < "$OUTPUT" | tr -d ' ') bytes, $(wc -l < "$OUTPUT" | tr -d ' ') lines"
echo
bold  "  NEXT STEP: Upload '$OUTPUT' to Google NotebookLM as a source,"
bold  "  then chat with your live market snapshot immediately."
echo
