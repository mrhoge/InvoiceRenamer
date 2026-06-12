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
import time
from datetime import datetime
from invoice_renamer.logic.config_manager import ConfigManager
from invoice_renamer.utils.constants import (
    PROJECT_NAME,
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_FILE_PREFIX,
    LOG_RETENTION_DAYS,
)

# 古いログの削除は起動ごとに1回で十分なため、実行済みフラグで多重実行を防ぐ
_old_logs_cleaned = False


def _cleanup_old_logs(log_dir, retention_days=LOG_RETENTION_DAYS):
    """保持期限を過ぎたログファイルを削除する

    ログには処理したファイル名（＝領収書の内容）が含まれ得るため、
    プライバシー保護の観点から一定期間で削除する。
    対象はこのAPが生成したログ（プレフィックス・拡張子が一致するもの）のみ。
    削除に失敗してもAPの起動は妨げない。

    Args:
        log_dir (str): ログファイル保存先ディレクトリ
        retention_days (int): 保持日数。これより古いログを削除する
    """
    global _old_logs_cleaned
    if _old_logs_cleaned:
        return
    _old_logs_cleaned = True

    cutoff = time.time() - retention_days * 24 * 60 * 60
    try:
        for name in os.listdir(log_dir):
            if not (name.startswith(DEFAULT_LOG_FILE_PREFIX) and name.endswith('.log')):
                continue
            path = os.path.join(log_dir, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                # 使用中・権限エラー等は無視して次のファイルへ
                pass
    except OSError:
        # ディレクトリが読めない場合も起動は継続する
        pass


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

    # 保持期限を過ぎた古いログを削除（起動ごとに1回だけ実行される）
    _cleanup_old_logs(log_dir)

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


