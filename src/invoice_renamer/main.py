"""
InvoiceRenamer メインアプリケーション

PDFビューアーアプリケーションのエントリーポイント。
設定に基づいてPDFハンドラーを初期化し、UIを起動する。

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""
import sys
import os
import platform
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from invoice_renamer.ui.pdf_viewer import PDFViewerApp
from invoice_renamer.logic.config_manager import ConfigManager
from invoice_renamer.logic.pdf_handlers import PyMuPDFHandler, PDF2ImageHandler
from invoice_renamer.utils.error_handler import ErrorHandler, ErrorType
from invoice_renamer.utils.logger import setup_logger

def create_pdf_handler(error_handler: ErrorHandler):
    """設定に基づいてPDFハンドラーを作成

    Args:
        error_handler (ErrorHandler): エラーハンドラーのインスタンス

    Returns:
        PDFHandler: 設定されたPDFハンドラー（PyMuPDFまたはPDF2Image）
        エラー時はデフォルトでPyMuPDFHandlerを返す

    Raises:
        ValueError: 未知のPDFハンドラーが設定されている場合
    """
    try:
        config = ConfigManager()
        handler_type = config.get_pdf_handler()

        if handler_type.lower() == 'pymupdf':
            return PyMuPDFHandler()
        elif handler_type.lower() == 'pdf2image':
            return PDF2ImageHandler()
        else:
            raise ValueError(f"未知のPDFハンドラが指定されています: {handler_type}")
            
    except Exception as e:
        error_handler.handle_error(
            e,
            ErrorType.CONFIG_FILE_ERROR,
            show_dialog=True,
            additional_info="PDFハンドラーの設定を確認してください"
        )
        # デフォルトでPyMuPDFHandlerを返す
        return PyMuPDFHandler()


def main():
    """メインアプリケーション起動関数

    アプリケーションの初期化と起動を行う。
    ロガー、エラーハンドラー、PDFハンドラーを設定し、
    PDFビューアーUIを表示する。

    Raises:
        ImportError: 必要なライブラリが不足している場合
        MemoryError: メモリ不足の場合
        Exception: その他の予期しないエラー
    """
    # ロガーとエラーハンドラーの初期化
    logger = setup_logger('invoice_renamer.main')
    error_handler = ErrorHandler(logger)

    try:
        # Windows環境の場合、アプリケーションID設定（タスクバーアイコン用）
        # この設定はQApplication作成前に行う必要がある
        if platform.system() == 'Windows':
            try:
                import ctypes
                myappid = 'mrhoge.invoicerenamer.pdfviewer.1.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
                logger.info("Windows AppUserModelIDを設定しました（タスクバーアイコン用）")
            except Exception as e:
                logger.warning(f"Windows AppUserModelIDの設定に失敗しました: {e}")

        app = QApplication(sys.argv)

        # PDFハンドラーの作成
        pdf_handler = create_pdf_handler(error_handler)

        # メインアプリケーションの起動（アイコン設定はPDFViewerApp内で実行）
        viewer = PDFViewerApp(pdf_handler)
        viewer.show()

        logger.info("アプリケーションを開始しました")
        sys.exit(app.exec())

    except ImportError as e:
        # 必要なライブラリが不足している場合
        error_handler.handle_error(
            e,
            ErrorType.UNKNOWN_ERROR,
            show_dialog=True,
            additional_info="必要なライブラリがインストールされていない可能性があります"
        )
        sys.exit(1)
        
    except MemoryError as e:
        # メモリ不足の場合
        error_handler.handle_error(
            e,
            ErrorType.MEMORY_ERROR,
            show_dialog=True
        )
        sys.exit(1)
        
    except Exception as e:
        # その他の予期しないエラー
        error_handler.handle_error(
            e,
            ErrorType.UNKNOWN_ERROR,
            show_dialog=True,
            additional_info="アプリケーションの起動に失敗しました"
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
