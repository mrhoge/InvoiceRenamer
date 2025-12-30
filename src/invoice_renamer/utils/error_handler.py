"""
エラーハンドリングユーティリティ

アプリケーション全体で使用するエラー種別の定義と
ユーザーフレンドリーなエラーメッセージを提供

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""

import os
import logging
from enum import Enum
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QMessageBox, QWidget


class ErrorType(Enum):
    """エラー種別の定義"""
    # ファイル関連エラー
    FILE_NOT_FOUND = "file_not_found"
    FILE_PERMISSION_DENIED = "file_permission_denied"
    FILE_CORRUPTED = "file_corrupted"
    FILE_UNSUPPORTED_FORMAT = "file_unsupported_format"
    
    # PDF関連エラー
    PDF_DAMAGED = "pdf_damaged"
    PDF_PASSWORD_PROTECTED = "pdf_password_protected"
    PDF_HANDLER_ERROR = "pdf_handler_error"
    
    # OCR関連エラー
    OCR_TESSERACT_NOT_FOUND = "ocr_tesseract_not_found"
    OCR_LANGUAGE_DATA_MISSING = "ocr_language_data_missing"
    OCR_PROCESSING_FAILED = "ocr_processing_failed"
    OCR_IMAGE_TOO_LARGE = "ocr_image_too_large"
    
    # システム関連エラー
    MEMORY_ERROR = "memory_error"
    DISK_SPACE_ERROR = "disk_space_error"
    NETWORK_ERROR = "network_error"
    
    # 設定関連エラー
    CONFIG_FILE_ERROR = "config_file_error"
    CONFIG_INVALID_VALUE = "config_invalid_value"
    
    # 一般的なエラー
    UNKNOWN_ERROR = "unknown_error"
    OPERATION_CANCELLED = "operation_cancelled"


class ErrorMessages:
    """ユーザーフレンドリーなエラーメッセージ"""
    
    MESSAGES = {
        ErrorType.FILE_NOT_FOUND: {
            "title": "ファイルが見つかりません",
            "message": "指定されたファイルが存在しません。\nファイルパスを確認してください。",
            "solution": "• ファイルが移動または削除されていないか確認\n• ファイルパスが正しいか確認"
        },
        ErrorType.FILE_PERMISSION_DENIED: {
            "title": "ファイルアクセスエラー",
            "message": "ファイルにアクセスする権限がありません。",
            "solution": "• ファイルの読み取り権限を確認\n• 管理者として実行してみる"
        },
        ErrorType.FILE_CORRUPTED: {
            "title": "ファイル破損エラー",
            "message": "ファイルが破損している可能性があります。",
            "solution": "• 別のファイルで試す\n• ファイルを再ダウンロードする"
        },
        ErrorType.PDF_DAMAGED: {
            "title": "PDF読み込みエラー",
            "message": "PDFファイルが破損しているか、サポートされていない形式です。",
            "solution": "• 別のPDFビューアで開けるか確認\n• PDFを再作成または修復する"
        },
        ErrorType.PDF_PASSWORD_PROTECTED: {
            "title": "パスワード保護PDF",
            "message": "このPDFはパスワードで保護されています。",
            "solution": "• パスワードを解除してから再度お試しください"
        },
        ErrorType.OCR_TESSERACT_NOT_FOUND: {
            "title": "OCRエンジンエラー",
            "message": "OCRエンジン（Tesseract）が見つかりません。",
            "solution": "• Tesseractをインストールしてください\n• パスが正しく設定されているか確認"
        },
        ErrorType.OCR_LANGUAGE_DATA_MISSING: {
            "title": "OCR言語データエラー",
            "message": "選択された言語のOCRデータが見つかりません。",
            "solution": "• 必要な言語データをインストールしてください\n• 別の言語設定を試してください"
        },
        ErrorType.MEMORY_ERROR: {
            "title": "メモリ不足エラー",
            "message": "処理に必要なメモリが不足しています。",
            "solution": "• 他のアプリケーションを終了してください\n• より小さなファイルで試してください"
        },
        ErrorType.CONFIG_FILE_ERROR: {
            "title": "設定ファイルエラー",
            "message": "設定ファイルの読み込みに失敗しました。",
            "solution": "• 設定ファイルを削除して初期設定を復元\n• 手動で設定ファイルを修正"
        },
        ErrorType.UNKNOWN_ERROR: {
            "title": "予期しないエラー",
            "message": "予期しないエラーが発生しました。",
            "solution": "• アプリケーションを再起動してください\n• 問題が続く場合はログファイルを確認"
        }
    }
    
    @classmethod
    def get_message(cls, error_type: ErrorType) -> Dict[str, str]:
        """エラータイプに対応するメッセージを取得"""
        return cls.MESSAGES.get(error_type, cls.MESSAGES[ErrorType.UNKNOWN_ERROR])


class ErrorHandler:
    """エラーハンドリングのユーティリティクラス"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def handle_error(self, 
                    error: Exception, 
                    error_type: ErrorType, 
                    parent: Optional[QWidget] = None,
                    show_dialog: bool = True,
                    additional_info: Optional[str] = None) -> None:
        """
        エラーを適切にハンドリング
        
        Args:
            error: 発生した例外
            error_type: エラーの種別
            parent: ダイアログの親ウィジェット
            show_dialog: エラーダイアログを表示するか
            additional_info: 追加情報
        """
        # ログに記録
        self.logger.error(f"{error_type.value}: {str(error)}", exc_info=True)
        if additional_info:
            self.logger.error(f"追加情報: {additional_info}")
        
        # ユーザーにダイアログ表示
        if show_dialog:
            self._show_error_dialog(error_type, parent, additional_info)
    
    def _show_error_dialog(self, 
                          error_type: ErrorType, 
                          parent: Optional[QWidget] = None,
                          additional_info: Optional[str] = None) -> None:
        """エラーダイアログを表示"""
        message_info = ErrorMessages.get_message(error_type)
        
        # メッセージテキストを構築
        message_text = message_info["message"]
        if additional_info:
            message_text += f"\n\n詳細: {additional_info}"
        message_text += f"\n\n解決方法:\n{message_info['solution']}"
        
        # ダイアログを表示
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(message_info["title"])
        msg_box.setText(message_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    @staticmethod
    def classify_file_error(file_path: str, exception: Exception) -> ErrorType:
        """ファイル関連エラーを分類"""
        if isinstance(exception, FileNotFoundError):
            return ErrorType.FILE_NOT_FOUND
        elif isinstance(exception, PermissionError):
            return ErrorType.FILE_PERMISSION_DENIED
        elif isinstance(exception, IsADirectoryError):
            return ErrorType.FILE_UNSUPPORTED_FORMAT
        elif "corrupt" in str(exception).lower() or "damaged" in str(exception).lower():
            return ErrorType.FILE_CORRUPTED
        else:
            return ErrorType.UNKNOWN_ERROR
    
    @staticmethod
    def classify_pdf_error(exception: Exception) -> ErrorType:
        """PDF関連エラーを分類"""
        error_str = str(exception).lower()
        
        if "password" in error_str or "encrypted" in error_str:
            return ErrorType.PDF_PASSWORD_PROTECTED
        elif "corrupt" in error_str or "damaged" in error_str or "invalid" in error_str:
            return ErrorType.PDF_DAMAGED
        else:
            return ErrorType.PDF_HANDLER_ERROR
    
    @staticmethod
    def classify_ocr_error(exception: Exception) -> ErrorType:
        """OCR関連エラーを分類"""
        error_str = str(exception).lower()
        
        if "tesseract" in error_str and ("not found" in error_str or "command not found" in error_str):
            return ErrorType.OCR_TESSERACT_NOT_FOUND
        elif "language" in error_str or "traineddata" in error_str:
            return ErrorType.OCR_LANGUAGE_DATA_MISSING
        elif "memory" in error_str or "image too large" in error_str:
            return ErrorType.OCR_IMAGE_TOO_LARGE
        else:
            return ErrorType.OCR_PROCESSING_FAILED