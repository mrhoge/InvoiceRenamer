#!/bin/bash
# Invoice Renamer 実行スクリプト (Linux/macOS用)
# このスクリプトはPYTHONPATHを設定してmain.pyを実行します

# スクリプトのディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# PYTHONPATHにsrcディレクトリを追加
export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"

# main.pyを実行
python3 "${SCRIPT_DIR}/main.py" "$@"
