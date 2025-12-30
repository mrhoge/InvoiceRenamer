"""
設定管理モジュール

TOMLファイルから設定を読み込み、アプリケーション全体で使用する
設定値を提供する。設定ファイルが存在しない場合はデフォルト値を使用。

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""
import tomllib
import os

class ConfigManager:
    """設定管理クラス

    TOMLファイルから設定を読み込み、各種設定値へのアクセスを提供。
    ロギング設定、PDFハンドラー設定などを管理する。

    Attributes:
        config (dict): 読み込まれた設定情報
    """

    def __init__(self, config_path='config.toml'):
        """ConfigManagerを初期化

        Args:
            config_path (str): 設定ファイルのパス（デフォルト: 'config.toml'）
        """
        self.config = {}
        if os.path.exists(config_path):
            with open(config_path, 'rb') as f:
                self.config = tomllib.load(f)
        else:
            self._set_defaults()

    def _set_defaults(self):
        """デフォルト設定の定義

        設定ファイルが存在しない場合に使用されるデフォルト値を設定。
        ロギング設定とPDFハンドラー設定を含む。
        """
        # 設定ファイルが存在しない場合の初期値
        self.config = {
            'logging': {
                'handlers': {
                    'console': {'level': 'INFO'},
                    'file': {'level': 'DEBUG'}
                },
                'file': {
                    'directory': 'logs',
                    'name': 'application.log'
                },
                'format': {
                    'console': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'file': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
                }
            },
            'pdf': {
                'handler': 'pymupdf'
            },
            'ocr': {
                'y_coordinate_tolerance': 2.0
            }
        }

    def get_console_log_level(self) -> str:
        """コンソール出力のログレベルを取得

        Returns:
            str: ログレベル（'INFO', 'DEBUG', 'WARNING', 'ERROR'等）
        """
        return self.config.get('logging', {}).get('handlers', {}).get('console', {}).get('level', 'INFO')

    def get_file_log_level(self) -> str:
        """ファイル出力のログレベルを取得

        Returns:
            str: ログレベル（デフォルト: 'DEBUG'）
        """
        return self.config.get('logging', {}).get('handlers', {}).get('file', {}).get('level', 'DEBUG')

    def get_log_directory(self) -> str:
        """ログファイルの出力ディレクトリを取得

        Returns:
            str: ログディレクトリのパス（デフォルト: 'logs'）
        """
        return self.config.get('logging', {}).get('handlers', {}).get('file', {}).get('directory', 'logs')

    def get_log_filename(self) -> str:
        """ログファイルのベース名を取得

        Returns:
            str: ログファイル名（デフォルト: 'application.log'）
        """
        return self.config.get('logging', {}).get('handlers', {}).get('file', {}).get('name', 'application.log')

    def get_console_log_format(self) -> str:
        """コンソール出力のログフォーマットを取得

        Returns:
            str: ログフォーマット文字列
        """
        return self.config.get('logging', {}).get('format', {}).get('console', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    def get_file_log_format(self) -> str:
        """ファイル出力のログフォーマットを取得

        Returns:
            str: ログフォーマット文字列（ファイル名と行番号を含む）
        """
        return self.config.get('logging', {}).get('format', {}).get('file', '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    def get_pdf_handler(self) -> str:
        """使用するPDFハンドラーの種類を取得

        Returns:
            str: PDFハンドラー名（'pymupdf' または 'pdf2image'）
        """
        return self.config.get('pdf', {}).get('handler', 'pymupdf')

    def get_y_coordinate_tolerance(self) -> float:
        """テキスト要素ソート時のY座標許容誤差を取得

        同じ行と見なすY座標の差分の範囲をポイント単位で取得。
        和暦などで数字と漢字のY座標が微妙にずれている場合に対応。

        Returns:
            float: Y座標許容誤差（ポイント単位、デフォルト: 2.0）
        """
        return self.config.get('ocr', {}).get('y_coordinate_tolerance', 2.0)


