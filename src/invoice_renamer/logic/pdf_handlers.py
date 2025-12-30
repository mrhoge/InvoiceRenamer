"""
PDFハンドラーモジュール

PDFファイルの読み込み、プレビュー生成、テキスト抽出などを行う。
PyMuPDFとpdf2imageの2つの実装を提供し、設定により切り替え可能。

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from PySide6.QtGui import QPixmap, QImage
import fitz  # PyMuPDF
from pdf2image import convert_from_path
import os
from invoice_renamer.utils.error_handler import ErrorHandler, ErrorType
from invoice_renamer.utils.logger import setup_logger

# ウィジェット名
BTN_CHOOSE_PDF_FOLDER = "PDFフォルダを選択"

# メッセージ
SELECTED_PDF_NAME = "選択されたPDF: "

class PDFHandler(ABC):
    """PDFハンドラーの抽象基底クラス

    PDFの読み込み、プレビュー生成、テキスト抽出などの
    共通インターフェースを定義する。
    依存性の注入パターンを使用して、実装クラスを切り替え可能。

    Attributes:
        current_pdf: 現在開いているPDFドキュメント
        total_pages (int): PDFの総ページ数
        logger: ロガーインスタンス
        error_handler (ErrorHandler): エラーハンドラーインスタンス
    """
    # configの値により、実行するクラスを随時変更する（依存性の注入）

    def __init__(self):
        self.current_pdf = None
        self.total_pages = 0
        self.logger = setup_logger('invoice_renamer.pdf_handlers')
        self.error_handler = ErrorHandler(self.logger)

    @abstractmethod
    def get_preview(self, pdf_path: str, page: int = 0) -> Optional[QPixmap]:
        """PDFのプレビュー画像を取得

        Args:
            pdf_path (str): PDFファイルのパス
            page (int): 取得対象のページ番号

        Returns:
            Optional[QPixmap]: プレビュー画像。エラー時はNone
        """
        # try:
        #     if not pdf_path:
        #         raise ValueError("PDFファイルパスが指定されていないか、正しくありません")
        #     if page < 0:
        #         raise ValueError("ページ番号が不正です。")
        #     return None
        # except Exception as e:
        #     print(f"プレビュー生成エラー: {e}")
        #     return None
        pass

    @abstractmethod
    def get_text(self, pdf_path: str, page: Optional[int] = None) -> str:
        """PDFからテキストを抽出

        Args:
            pdf_path (str): PDFファイルのパス
            page (Optional[int]): 特定のページを取得する場合はページ番号、Noneの場合は全ページ取得

        Returns:
            str: 抽出したテキスト。エラー時はエラーメッセージ
        """
        # try:
        #     if not pdf_path:
        #         raise ValueError("PDFファイルパスが指定されていないか、正しくありません")
        #     if page < 0:
        #         raise ValueError("ページ番号が不正です。")
        #     return None
        # except Exception as e:
        #     return f"テキスト抽出エラー: {e}"
        pass

    @abstractmethod
    def get_images(self, pdf_path: str, dpi: int = 300) -> list[QPixmap]:
        """PDFから画像を抽出

        Args:
            pdf_path (str): PDFファイルのパス
            dpi (int, optional): _description_. Defaults to 300.

        Returns:
            list[QPixmap]: _description_
        """
        pass

    def load_pdf(self, pdf_path: str, parent_widget=None) -> bool:
        """PDFファイルをロードし、総ページ数を取得

        Args:
            pdf_path (str): PDFファイルのパス
            parent_widget: エラーダイアログの親ウィジェット

        Returns:
            bool: 読み込み成功時True、失敗時False
        """
        try:
            # ファイル存在チェック
            if not os.path.exists(pdf_path):
                error_type = ErrorType.FILE_NOT_FOUND
                self.error_handler.handle_error(
                    FileNotFoundError(f"File not found: {pdf_path}"),
                    error_type,
                    parent_widget,
                    additional_info=f"ファイルパス: {pdf_path}"
                )
                return False

            # ゼロバイトファイルチェック
            if os.path.getsize(pdf_path) == 0:
                self.logger.warning(f"ゼロバイトファイルをスキップ: {pdf_path}")
                error_type = ErrorType.FILE_CORRUPTED
                self.error_handler.handle_error(
                    ValueError("File is empty (0 bytes)"),
                    error_type,
                    parent_widget,
                    additional_info=f"ファイルサイズ: 0バイト\nファイルパス: {pdf_path}"
                )
                return False

            # ファイルアクセス権限チェック
            if not os.access(pdf_path, os.R_OK):
                error_type = ErrorType.FILE_PERMISSION_DENIED
                self.error_handler.handle_error(
                    PermissionError(f"Permission denied: {pdf_path}"),
                    error_type,
                    parent_widget,
                    additional_info=f"ファイルパス: {pdf_path}"
                )
                return False

            # PyMuPDFでPDFを開く
            try:
                doc = fitz.open(pdf_path)
            except fitz.FileDataError as e:
                # PDFファイル構造が破損している場合
                self.logger.error(f"破損したPDFファイル: {pdf_path} - {str(e)}")
                error_type = ErrorType.FILE_CORRUPTED
                self.error_handler.handle_error(
                    e,
                    error_type,
                    parent_widget,
                    additional_info=f"PDFファイルの構造が破損しています\nファイルパス: {pdf_path}"
                )
                return False

            # パスワード保護チェック
            if doc.is_encrypted:
                self.logger.warning(f"パスワード保護のためスキップ: {pdf_path}")
                error_type = ErrorType.FILE_PERMISSION_DENIED
                self.error_handler.handle_error(
                    PermissionError("PDF is password protected"),
                    error_type,
                    parent_widget,
                    additional_info=f"このPDFはパスワードで保護されています\nパスワード保護を解除してから再度お試しください\n\nファイルパス: {pdf_path}"
                )
                doc.close()
                return False

            # ページ数チェック
            if doc.page_count == 0:
                error_type = ErrorType.FILE_CORRUPTED
                self.error_handler.handle_error(
                    ValueError("PDF contains no pages"),
                    error_type,
                    parent_widget,
                    additional_info="PDFにページが含まれていません"
                )
                doc.close()
                return False

            self.total_pages = doc.page_count
            self.current_pdf = doc
            self.logger.info(f"PDF読み込み成功: {pdf_path} ({self.total_pages}ページ)")
            return True

        except MemoryError as e:
            # メモリ不足エラー
            error_type = ErrorType.MEMORY_ERROR
            self.error_handler.handle_error(e, error_type, parent_widget)
            self.close()
            return False
            
        except (FileNotFoundError, PermissionError) as e:
            # ファイル関連エラー（上で個別処理済みだが念のため）
            error_type = self.error_handler.classify_file_error(pdf_path, e)
            self.error_handler.handle_error(e, error_type, parent_widget)
            self.close()
            return False
            
        except Exception as e:
            # その他の予期しないエラー
            error_type = self.error_handler.classify_pdf_error(e)
            self.error_handler.handle_error(e, error_type, parent_widget)
            self.close()
            return False

    def get_page_count(self) -> int:
        """総ページ数を返す

        Returns:
            int: 総ページ数。PDFが未だ読込されていない場合は0
        """
        return self.total_pages

    def close(self) -> None:
        """PDFファイルを閉じる"""
        if hasattr(self, 'current_pdf') and self.current_pdf is not None:
            try:
                self.current_pdf.close()
            except (ValueError, RuntimeError):
                # 既にクローズされている場合は無視
                pass
        self.current_pdf = None
        self.total_pages = 0

class PyMuPDFHandler(PDFHandler):
    """PyMuPDFを使用するPDFハンドラー実装

    PyMuPDF (fitz) ライブラリを使用してPDFの処理を行う。
    高速かつ機能豊富で、推奨される実装。
    """

    def get_preview(self, pdf_path: str, page: int = 0) -> Optional[QPixmap]:
        """PDFのプレビュー画像を生成

        Args:
            pdf_path (str): PDFファイルのパス
            page (int): ページ番号（0から始まる）。デフォルトは0

        Returns:
            Optional[QPixmap]: プレビュー画像。エラー時はNone

        Note:
            2倍の解像度（Matrix(2,2)）でレンダリングして高品質な画像を生成
        """
        try:
            # 既存PDFが開かれているかを確認
            if not self.current_pdf or self.current_pdf.name != pdf_path:
                self.load_pdf(pdf_path)

            if not self.current_pdf or not (0 <= page < self.total_pages):
                return None

            pdf_page = self.current_pdf[page]
            pix = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            return QPixmap.fromImage(img)

        except Exception as e:
            print(f"プレビュー生成エラー: {e}")
            return None

    def get_text(self, pdf_path: str, page: Optional[int] = None) -> str:
        """PDFからテキストを抽出

        Args:
            pdf_path (str): PDFファイルのパス
            page (Optional[int]): 特定のページ番号（0から始まる）
                                 Noneの場合は全ページのテキストを抽出

        Returns:
            str: 抽出されたテキスト。エラー時はエラーメッセージ
        """
        try:
            # 既存PDFが開かれているかを確認
            if not self.current_pdf or self.current_pdf.name != pdf_path:
                self.load_pdf(pdf_path)

            if not self.current_pdf:
                return "PDFファイルを開けませんでした"

            if page is None:
                # 全ページのテキストを取得
                return "\n".join(p.get_text() for p in self.current_pdf)
            elif 0 <= page < self.total_pages:
                return self.current_pdf[page].get_text()
            else:
                return "指定されたページは存在しません"

            """以下は一気にPDF全体をロードする処理。いつか実装するかも"""
            # doc = fitz.open(pdf_path)
            # text = ""
            # for page in doc:
            #     text += page.get_text()
            # doc.close()
            # return text
            """一気にPDF全体をロードする処理。ここまで"""
        except Exception as e:
            return f"テキスト抽出エラー: {e}"

    def close(self) -> None:
        """PDFファイルを閉じてリソースを解放

        現在開いているPDFドキュメントをクローズし、
        親クラスのcloseメソッドを呼び出してステータスをリセット。
        """
        if self.current_pdf:
            self.current_pdf.close()
        super().close()

    def get_images(self, pdf_path: str, dpi: int = 300) -> List[QPixmap]:
        """PDFから画像を抽出

        Args:
            pdf_path (str): PDFファイルのパス
            dpi (int): 解像度（デフォルトは300、現在未使用）

        Returns:
            List[QPixmap]: 抽出された画像のリスト。エラー時は空リスト

        Note:
            PDF内に埋め込まれた画像を抽出する。
            各ページから画像を検出し、QPixmapに変換して返す。
        """
        try:
            if not self.current_pdf or self.current_pdf.name != pdf_path:
                self.load_pdf(pdf_path)

            if not self.current_pdf:
                return [] # PDFファイルが開けない場合は空リストを返す

            images = []
            for page in self.current_pdf:
                # PyMuPDFでの画像抽出処理
                image_list = page.get_images()
                if image_list: # 画像が取得できた場合のみ追加
                    for img in image_list:
                        xref = img[0]
                        base_image = self.current_pdf.extract_image(xref)
                        image_data = QImage.fromData(base_image["image"])
                        images.append(QPixmap.fromImage(image_data))
            return images

        except Exception as e:
            print(f"画像抽出エラー: {e}")
            return []

class PDF2ImageHandler(PDFHandler):
    """pdf2imageを使用するPDFハンドラー実装

    pdf2imageライブラリを使用してPDFの処理を行う。
    学習・参考用の実装で、現在は機能が限定的。

    Note:
        こちらの機能は学習用に実装したため、必要になるまで更新停止の予定
    """
    def get_preview(self, pdf_path: str, page:int = 0) -> Optional[QPixmap]:
        """PDFのプレビュー画像を生成

        Args:
            pdf_path (str): PDFファイルのパス
            page (int): ページ番号（0から始まる）。デフォルトは0

        Returns:
            Optional[QPixmap]: プレビュー画像。エラー時はNone

        Note:
            pdf2imageを使用してPDFをPIL画像に変換
        """
        try:
            images = convert_from_path(pdf_path, first_page=page+1, last_page=page+1)
            if images:
                return images[0].toqpixmap()
        except Exception as e:
            print(f"プレビュー生成エラー: {e}")
        return None

    def get_text(self, pdf_path: str) -> str:
        """PDFからテキストを抽出（未実装）

        Args:
            pdf_path (str): PDFファイルのパス

        Returns:
            str: エラーメッセージ（テキスト抽出未対応）

        Note:
            pdf2imageはテキスト抽出に対応していないため、
            別のライブラリ（例：PyPDF2）を使用する必要がある
        """
        return "PDF2Imageハンドラーではテキスト抽出未対応"

