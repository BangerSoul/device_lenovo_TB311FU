#!/usr/bin/env bash
# ==============================================================================
# Wrapper for Complete Official Latest Stock Firmware Flasher
# Target: Lenovo Tab M11 (TB311FU / poplar, MT6768 / MT8786, Serial: HNQ09EZD)
# Package: TB311FU_ROW_OPEN_USER_M1457.5_W_ZUI_17.5.36.508_ST_261024
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="/tmp/mtkclient:${PYTHONPATH:-}"

python3 "$SCRIPT_DIR/flash_latest_stock.py" "$@"
