"""
AP用のロガーユーティリティモジュール
このモジュールは、APプロジェクト内で使用されるロガーのセットアップと管理を提供します。

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""

import logging
import os
from datetime import datetime
from invoice_renamer.logic.config_manager import ConfigManager
from invoice_renamer.utils.constants import PROJECT_NAME, DEFAULT_LOG_DIR

def setup_logger(module_name=None, log_dir="logs"):
    """AP用のロガーセットアップ

    Args:
        module_name (str, optional): モジュール名。指定がない場合はプロジェクト名を仕様
        log_dir (str): ログファイル保存先ディレクトリ
    Returns:
        logging.Logger: 設定済みのロガーインスタンス
    """
    # ConfigNamagerから設定を取得
    config = ConfigManager()
    console_log_level = getattr(logging, config.get_console_log_level().upper())
    file_log_level = getattr(logging, config.get_file_log_level().upper())

    # ログフォーマットを取得
    console_log_format = config.get_console_log_format()
    file_log_format = config.get_file_log_format()

    # ログディレクトリが存在しない場合は作成
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # ロガー名の設定
    logger_name = module_name if module_name else PROJECT_NAME
    logger = logging.getLogger(logger_name)
    logger.setLevel(min(console_log_level, file_log_level)) # 低い方のレベルを設定

    # ハンドラーが存在しない場合に追加する
    if not logger.handlers:
        # 現在時刻をファイル名に含める
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'{PROJECT_NAME}_{timestamp}.log')

        # ファイルハンドラ
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(file_log_level)
        file_handler.setFormatter(logging.Formatter(file_log_format))

        # コンソールハンドラ設定
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_log_level)
        console_handler.setFormatter(logging.Formatter(console_log_format))

        # ハンドラの追加
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


