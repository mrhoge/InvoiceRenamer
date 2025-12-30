"""プロジェクト全体で使用する定数を定義"""
"""
Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""

# プロジェクト基本情報
PROJECT_NAME = "invoice_renamer"

# ディレクトリ構造
WORK_FOLDER_NAME = "work"

# ログ関係の定数（デフォルト値）
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DEFAULT_LOG_FILE_PREFIX = f"{PROJECT_NAME}_"

# 拡張子
FILE_EXTENTION_NAME = ".pdf"

# UIテキスト
UI_EXTRACTED_TEXT = "抽出されたテキスト"
UI_SELECTED_PDF_NAME = "選択されたPDF: "
UI_BTN_CHOOSE_PDF_FOLDER = "PDFフォルダを選択"
UI_SELECTED_PDF_NAME = "選択されたPDF: "

# 実行時メッセージ
MESSAGE_VIEWER_INITIALIZED = "PDFビューアが初期化されました"
MESSAGE_PDF_HANDLER_NOT_FOUND = "指定されたPDFハンドラーが見つかりません: {handler_type}"

# ウィジェット名
BTN_CHOOSE_PDF_FOLDER = "PDFフォルダを選択"

# ログレベル
LOG_LEVEL_DEBUG = "DEBUG"

