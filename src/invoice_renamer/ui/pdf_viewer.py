"""
PDFビューアーUIモジュール

PDFファイルの表示、範囲選択、OCR分析、ファイル名変更などの
UIコンポーネントを提供するメインモジュール。

主な機能:
- PDFファイルのプレビュー表示
- マウスドラッグによる範囲選択
- 選択範囲のOCR分析（非同期処理）
- PDFファイル名の変更
- ズーム機能
- OCR言語設定

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
import re
import csv
import sys
import shutil
from typing import Optional, List
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout,
                            QPushButton, QListWidget, QWidget, QFileDialog,
                            QLabel, QTextEdit, QLineEdit, QMessageBox,
                            QListWidgetItem, QScrollArea, QFrame, QCheckBox,
                            QTextBrowser, QApplication, QComboBox)
from PySide6.QtCore import Qt, Signal, QRect, QPoint, QTimer, QThread, QStandardPaths, QUrl, QSettings
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QMouseEvent
from pdf2image import convert_from_path
from invoice_renamer.logic.pdf_handlers import PDFHandler, PyMuPDFHandler, PDF2ImageHandler
from invoice_renamer.logic.selection_analyzer_v6 import SelectionAnalyzer, SelectionData
from invoice_renamer.utils.logger import setup_logger
from invoice_renamer.utils import constants
from invoice_renamer.utils.error_handler import ErrorHandler, ErrorType


class AnalysisWorker(QThread):
    """選択範囲分析を非同期で実行するワーカースレッド

    UIをブロックせずにOCR分析を実行するためのワーカークラス。
    分析完了時またはエラー時にシグナルを発行する。

    Signals:
        analysis_finished: 分析完了時に結果リストを通知
        analysis_error: エラー発生時にエラーメッセージを通知

    Attributes:
        analyzer (SelectionAnalyzer): 分析器インスタンス
        selection_data (SelectionData): 選択範囲データ
        analysis_params (dict): 分析パラメータ
        quick_mode (bool): 高速モード
    """
    analysis_finished = Signal(list)  # 分析結果のシグナル
    analysis_error = Signal(str)  # エラーのシグナル

    def __init__(self, analyzer, selection_data, analysis_params, quick_mode=True):
        """ワーカーを初期化

        Args:
            analyzer (SelectionAnalyzer): 選択範囲分析器
            selection_data (SelectionData): 選択範囲データ
            analysis_params (dict): 分析パラメータ（ズーム、サイズ等）
            quick_mode (bool): 高速モード（デフォルト: True）
        """
        super().__init__()
        self.analyzer = analyzer
        self.selection_data = selection_data
        self.analysis_params = analysis_params
        self.quick_mode = quick_mode
    
    def run(self):
        """バックグラウンドで分析を実行

        ワーカースレッドのメイン処理。
        分析が成功すればanalysis_finishedシグナル、
        失敗すればanalysis_errorシグナルを発行。
        """
        try:
            results = self.analyzer.analyze_selection(self.selection_data, self.analysis_params, self.quick_mode)
            self.analysis_finished.emit(results)
        except Exception as e:
            self.analysis_error.emit(str(e))

class SelectableLabel(QLabel):
    """範囲選択可能なQLabelウィジェット

    マウスドラッグによる矩形範囲選択機能を持つラベル。
    PDF画像を表示し、ユーザーが範囲を選択できる。

    機能:
        - 左クリック+ドラッグ: 範囲選択（OCR分析用）
        - 右クリック+ドラッグ: パンニング（PDF表示の移動）

    Signals:
        selection_made: 範囲選択が完了した際にQRectを通知
        selection_cleared: 選択範囲がクリアされた際に通知

    Attributes:
        selection_start (QPoint): 選択開始点
        selection_end (QPoint): 選択終了点
        selecting (bool): 現在選択中かどうか
        selection_rect (QRect): 現在の選択矩形
        confirmed_selection (QRect): 確定した選択矩形
        mouse_moved (bool): マウスが移動したかのフラグ
        panning (bool): 現在パンニング中かどうか
        pan_start (QPoint): パンニング開始点
        scroll_area (QScrollArea): 親スクロールエリアへの参照
    """
    selection_made = Signal(QRect)
    selection_cleared = Signal()

    def __init__(self, parent=None):
        """SelectableLabelを初期化

        Args:
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.selection_start = QPoint()
        self.selection_end = QPoint()
        self.selecting = False
        self.selection_rect = QRect()
        self.confirmed_selection = QRect()  # 確定した選択範囲
        self.mouse_moved = False  # マウスが移動したかのフラグ

        # パンニング用の変数
        self.panning = False
        self.pan_start = QPoint()
        self.scroll_area = None  # QScrollAreaへの参照（後で設定）
        
    def mousePressEvent(self, event: QMouseEvent):
        """マウスボタン押下イベント

        左ボタン: 範囲選択開始
        右ボタン: パンニング開始

        Args:
            event (QMouseEvent): マウスイベント
        """
        if event.button() == Qt.LeftButton:
            self.selection_start = event.position().toPoint()
            self.selecting = True
            self.mouse_moved = False

            # 既存の選択範囲をクリア（新しい選択開始）
            self.selection_rect = QRect()
            self.update()
        elif event.button() == Qt.RightButton:
            # 右クリックでパンニング開始
            self.panning = True
            self.pan_start = event.globalPosition().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """マウス移動イベント

        左ボタン: 範囲選択
        右ボタン: パンニング（PDF表示の移動）

        Args:
            event (QMouseEvent): マウスイベント
        """
        if self.selecting and event.buttons() & Qt.LeftButton:
            self.selection_end = event.position().toPoint()
            self.selection_rect = QRect(self.selection_start, self.selection_end).normalized()
            self.mouse_moved = True
            self.update()
        elif self.panning and event.buttons() & Qt.RightButton:
            # パンニング処理
            if self.scroll_area:
                current_pos = event.globalPosition().toPoint()
                delta = current_pos - self.pan_start
                self.pan_start = current_pos

                # スクロールバーの位置を更新
                h_scroll = self.scroll_area.horizontalScrollBar()
                v_scroll = self.scroll_area.verticalScrollBar()
                h_scroll.setValue(h_scroll.value() - delta.x())
                v_scroll.setValue(v_scroll.value() - delta.y())
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """マウスボタン解放イベント

        Args:
            event (QMouseEvent): マウスイベント
        """
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False

            # マウスが移動していない場合（単なるクリック）
            if not self.mouse_moved:
                # 既存の選択範囲をクリア
                self.clear_selection()
                self.selection_cleared.emit()
            else:
                # 範囲選択の場合
                if self.selection_rect.width() > 10 and self.selection_rect.height() > 10:
                    self.confirmed_selection = self.selection_rect
                    self.selection_made.emit(self.selection_rect)
                else:
                    # 小さすぎる選択は無効
                    self.selection_rect = QRect()
                    self.update()
        elif event.button() == Qt.RightButton and self.panning:
            # パンニング終了
            self.panning = False
            self.setCursor(Qt.ArrowCursor)

        super().mouseReleaseEvent(event)
    
    def clear_selection(self):
        """選択範囲をクリア

        すべての選択状態をリセットし、画面を更新。
        """
        self.selection_rect = QRect()
        self.confirmed_selection = QRect()
        self.selecting = False
        self.update()
    
    def paintEvent(self, event):
        """ペイントイベント

        選択範囲を視覚的に描画する。
        選択中は点線の青い矩形、確定後は薄い青で表示。

        Args:
            event: ペイントイベント
        """
        super().paintEvent(event)
        
        # 現在選択中の範囲を描画
        if self.selecting and not self.selection_rect.isEmpty():
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.DashLine))
            painter.setBrush(QColor(0, 120, 215, 50))
            painter.drawRect(self.selection_rect)
        
        # 確定した選択範囲を描画（薄く表示）
        elif not self.confirmed_selection.isEmpty():
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.SolidLine))
            painter.setBrush(QColor(0, 120, 215, 20))
            painter.drawRect(self.confirmed_selection)


class AnalysisResultBubble(QFrame):
    """分析結果を表示するバブルウィジェット（コピー機能付き）

    OCR分析結果をポップアップバブルとして表示する。
    テキストのコピー機能とデバッグモード表示をサポート。

    Attributes:
        result_text (str): 表示するテキスト
        extracted_text (str): 抽出されたテキスト（コピー用）
        is_debug_mode (bool): デバッグモード（詳細情報を表示）
    """

    def __init__(self, result_text: str, position: QPoint, is_debug_mode: bool = False, extracted_text: str = None, parent=None):
        """分析結果バブルを初期化

        Args:
            result_text (str): 表示するテキスト
            position (QPoint): バブルの表示位置
            is_debug_mode (bool): デバッグモード（詳細情報表示）
            extracted_text (str): 抽出されたテキスト（通常モードでのコピー用）
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.result_text = result_text
        self.extracted_text = extracted_text if extracted_text is not None else result_text
        self.is_debug_mode = is_debug_mode

        # アプリケーションレベルのイベントフィルターをインストール
        # （バブル外のクリックを検出するため）
        QApplication.instance().installEventFilter(self)
        
        # メインレイアウト
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setLayout(main_layout)
        
        # バブル本体のフレーム
        bubble_frame = QFrame()
        bubble_frame.setStyleSheet(
            "QFrame { "
            "background-color: rgba(255, 255, 255, 240); "
            "border: 1px solid #ccc; "
            "border-radius: 8px; "
            "}"
        )
        
        bubble_layout = QVBoxLayout()
        bubble_layout.setContentsMargins(8, 8, 8, 8)
        bubble_frame.setLayout(bubble_layout)
        
        # ヘッダー（モード表示とボタン）
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 5)
        
        # モード表示ラベル
        mode_label = QLabel("🔧 デバッグモード" if is_debug_mode else "📄 通常モード")
        mode_label.setStyleSheet("color: #666; font-size: 10px; font-weight: bold;")
        header_layout.addWidget(mode_label)
        
        header_layout.addStretch()
        
        # コピーボタン
        copy_btn = QPushButton("📋 コピー")
        copy_btn.setFixedSize(60, 20)
        copy_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #007ACC; "
            "color: white; "
            "border: none; "
            "border-radius: 3px; "
            "font-size: 9px; "
            "} "
            "QPushButton:hover { "
            "background-color: #005a9e; "
            "}"
        )
        copy_btn.clicked.connect(self.copy_to_clipboard)
        header_layout.addWidget(copy_btn)
        
        # 閉じるボタン
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { "
            "background-color: #ff4444; "
            "color: white; "
            "border: none; "
            "border-radius: 3px; "
            "font-size: 10px; "
            "font-weight: bold; "
            "} "
            "QPushButton:hover { "
            "background-color: #cc0000; "
            "}"
        )
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        
        bubble_layout.addLayout(header_layout)
        
        # 結果テキストを表示（スクロール可能なテキストブラウザ）
        self.text_browser = QTextBrowser()
        self.text_browser.setPlainText(result_text)
        self.text_browser.setMaximumWidth(400)
        self.text_browser.setMaximumHeight(300)
        self.text_browser.setMinimumWidth(250)
        self.text_browser.setMinimumHeight(100)
        self.text_browser.setStyleSheet(
            "QTextBrowser { "
            "background-color: transparent; "
            "border: none; "
            "color: #333; "
            "font-family: 'Courier New', monospace; "
            "font-size: 11px; "
            "}"
        )
        bubble_layout.addWidget(self.text_browser)
        
        main_layout.addWidget(bubble_frame)
        
        # 位置を設定
        self.move(position)
        
        # 自動で消えるタイマー（デバッグモードでは長く表示）
        self.timer = QTimer()
        self.timer.timeout.connect(self.hide)
        timeout_duration = 15000 if is_debug_mode else 8000  # デバッグモード15秒、通常8秒
        self.timer.start(timeout_duration)
    
    def copy_to_clipboard(self):
        """テキストをクリップボードにコピー

        デバッグモード: 解析結果全体をコピー
        通常モード: 抽出されたテキストのみをコピー
        """
        clipboard = QApplication.clipboard()

        # デバッグモードでは解析結果全体、通常モードでは抽出テキストのみをコピー
        if self.is_debug_mode:
            clipboard.setText(self.result_text)
        else:
            clipboard.setText(self.extracted_text)

        # コピー完了を短時間表示
        original_text = self.text_browser.toPlainText()
        copy_mode = "解析結果全体" if self.is_debug_mode else "テキスト"
        self.text_browser.setPlainText(f"✅ {copy_mode}をクリップボードにコピーしました！")

        # 1秒後に元のテキストに戻す
        QTimer.singleShot(1000, lambda: self.text_browser.setPlainText(original_text))
    
    def mousePressEvent(self, event):
        # バブル内のクリックでは閉じない（コピー操作のため）
        event.accept()

    def eventFilter(self, obj, event):
        """アプリケーション全体のイベントをフィルタリング

        バブル外でマウスクリックが発生した場合、バブルを非表示にする。

        Args:
            obj: イベントが発生したオブジェクト
            event: 発生したイベント

        Returns:
            bool: イベントを処理した場合True、そうでない場合False
        """
        from PySide6.QtCore import QEvent

        # マウスボタン押下イベントをチェック
        if event.type() == QEvent.MouseButtonPress:
            # バブル内のクリックかどうかを判定
            click_pos = event.globalPosition().toPoint()
            if not self.geometry().contains(self.mapFromGlobal(click_pos)):
                # バブル外のクリックなので非表示
                self.hide()
                return False

        # ウィンドウのアクティブ化状態の変更をチェック（タスク切り替え）
        if event.type() == QEvent.ApplicationDeactivate:
            # 別のアプリケーションに切り替わったので非表示
            self.hide()
            return False

        # 通常の処理を継続
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        """バブルが非表示になる際の処理

        イベントフィルターを解除し、タイマーを停止する。

        Args:
            event: hideイベント
        """
        # イベントフィルターを解除
        QApplication.instance().removeEventFilter(self)

        # タイマーを停止
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()

        super().hideEvent(event)


class PDFViewerApp(QMainWindow):
    def __init__(self, pdf_handler: PDFHandler):
        super().__init__()

        # ロガーの初期化
        self.logger = setup_logger('invoice_renamer.pdf_viewer')
        self.pdf_handler = pdf_handler
        self.error_handler = ErrorHandler(self.logger)

        # QSettings の初期化（INIファイル形式で保存）
        # settings.ini はプロジェクトルートに作成され、.gitignore で除外される
        settings_path = os.path.join(os.getcwd(), "settings.ini")
        self.settings = QSettings(settings_path, QSettings.IniFormat)

        # 状態管理用の変数
        # 前回のフォルダパスを復元（同時に値のバリデーションを行う）
        self.current_folder = self._load_and_validate_last_folder()

        self.current_pdf_path = None
        self.current_page = 0
        self.total_pages = 0
        self.extracted_text_items = []  # 抽出されたテキストのリスト

        # 範囲選択関連
        self.selection_analyzer = SelectionAnalyzer()
        self.current_bubbles = []  # 表示中のバブルリスト
        self.debug_mode = False  # デバッグモードフラグ
        self.analysis_worker = None  # 分析ワーカー
        self.analysis_in_progress = False  # 分析実行中フラグ
        self.last_selection_rect = QRect()  # 最後の選択範囲

        # ズーム関連
        self.zoom_scale = 1.0  # 現在のズーム倍率
        self.min_zoom = 0.25  # 最小ズーム倍率
        self.max_zoom = 5.0   # 最大ズーム倍率
        self.zoom_step = 0.25  # ズームステップ

        self.setup_ui()
        self.setup_connections()
        self.logger.info(constants.MESSAGE_VIEWER_INITIALIZED)

        # 前回のフォルダが復元された場合はログ出力
        if self.current_folder:
            self.logger.info(f"前回のフォルダパスを復元: {self.current_folder}")

    def _load_and_validate_last_folder(self) -> Optional[str]:
        """前回のフォルダパスを読み込み、厳格にバリデーションする

        セキュリティチェック:
        - パスが文字列型であること
        - パスが空でないこと
        - 絶対パスであること
        - 実際に存在するディレクトリであること
        - 読み取り権限があること
        - 危険な文字が含まれていないこと

        Returns:
            Optional[str]: 検証済みのフォルダパス、または None（検証失敗時）
        """
        try:
            saved_folder = self.settings.value("last_folder_path", None)

            # 値が None または空の場合
            if not saved_folder:
                self.logger.info("前回のフォルダパスが保存されていません")
                return None

            # 文字列型でない場合（改ざん検知）
            if not isinstance(saved_folder, str):
                self.logger.warning(f"不正な型のフォルダパス（型: {type(saved_folder)}）を検出。デフォルト位置を使用します")
                return None

            # 空文字列の場合
            if not saved_folder.strip():
                self.logger.warning("空のフォルダパスを検出。デフォルト位置を使用します")
                return None

            # 絶対パスでない場合（セキュリティリスク）
            if not os.path.isabs(saved_folder):
                self.logger.warning(f"相対パス「{saved_folder}」を検出。セキュリティ上、デフォルト位置を使用します")
                return None

            # 危険な文字が含まれている場合（改ざん検知）
            dangerous_chars = ['\0', '\n', '\r', '\t']
            if any(char in saved_folder for char in dangerous_chars):
                self.logger.warning(f"危険な文字を含むパス「{saved_folder}」を検出。デフォルト位置を使用します")
                return None

            # ディレクトリが存在しない場合
            if not os.path.exists(saved_folder):
                self.logger.info(f"保存されたフォルダ「{saved_folder}」が存在しません。デフォルト位置を使用します")
                return None

            # ディレクトリでない場合（ファイルパスが指定されている）
            if not os.path.isdir(saved_folder):
                self.logger.warning(f"保存されたパス「{saved_folder}」はディレクトリではありません。デフォルト位置を使用します")
                return None

            # 読み取り権限がない場合
            if not os.access(saved_folder, os.R_OK):
                self.logger.warning(f"フォルダ「{saved_folder}」に読み取り権限がありません。デフォルト位置を使用します")
                return None

            # すべての検証をパス
            return saved_folder

        except Exception as e:
            self.logger.error(f"フォルダパスの検証中にエラーが発生したため、初期ディレクトリを返却します。: {e}")
            return None

    def setup_connections(self):
        """シグナルとスロットの接続"""
        # PDF選択ボタンの接続
        self.pdf_list_widget.itemDoubleClicked.connect(self.open_pdf)
        self.select_folder_btn.clicked.connect(self.select_pdf_folder)

        # ページコントロールボタンの接続
        self.prev_btn.clicked.connect(self.show_prev_page)
        self.next_btn.clicked.connect(self.show_next_page)
        
        # ズームコントロールボタンの接続
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_reset_btn.clicked.connect(self.reset_zoom)

        # ファイル名変更ボタンの接続
        self.rename_btn.clicked.connect(self.rename_current_file)

        # 元に戻すボタンの接続
        self.reset_filename_btn.clicked.connect(self.reset_filename)

        # テキストアイテムリストの接続
        self.text_items_list.itemDoubleClicked.connect(self.add_text_to_filename)
        
        # 範囲選択の接続
        self.preview_label.selection_made.connect(self.on_selection_made)
        self.preview_label.selection_cleared.connect(self.on_selection_cleared)
        
        # キーボードショートカットの設定
        from PySide6.QtGui import QShortcut, QKeySequence
        
        # Ctrl+0: ズームリセット
        zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        zoom_reset_shortcut.activated.connect(self.reset_zoom)
        
        # Ctrl++: ズームイン
        zoom_in_shortcut = QShortcut(QKeySequence("Ctrl++"), self)
        zoom_in_shortcut.activated.connect(self.zoom_in)
        
        # Ctrl+-: ズームアウト
        zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        zoom_out_shortcut.activated.connect(self.zoom_out)

    def wheelEvent(self, event):
        """Handles mouse wheel scroll events for page navigation and zooming.

        - Ctrl + Wheel: Zoom in/out
        - Wheel alone: Navigate pages (up=previous, down=next)
        """
        modifiers = event.modifiers()
        angle = event.angleDelta().y()
        
        if modifiers & Qt.ControlModifier:
            # Ctrl + ホイールでズーム
            if angle > 0:
                self.zoom_in()
            elif angle < 0:
                self.zoom_out()
            event.accept()
        else:
            # 通常のホイールでページ遷移
            if angle > 0:
                self.show_prev_page()
                event.accept()
            elif angle < 0:
                self.show_next_page()
                event.accept()
            else:
                super().wheelEvent(event)

    def show_prev_page(self):
        """前のページを表示"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_page_display()
            self.logger.info(f"前のページを表示: {self.current_page + 1}/{self.total_pages}")

    def show_next_page(self):
        """次のページを表示"""
        if self.current_page < self.total_pages -1:
            self.current_page += 1
            self.update_page_display()
            self.logger.info(f"次のページを表示: {self.current_page + 1}/{self.total_pages}")
    
    def zoom_in(self):
        """ズームイン"""
        if self.zoom_scale < self.max_zoom:
            self.zoom_scale = min(self.zoom_scale + self.zoom_step, self.max_zoom)
            self.update_page_display()
            self.logger.info(f"ズームイン: {self.zoom_scale:.2f}x")
    
    def zoom_out(self):
        """ズームアウト"""
        if self.zoom_scale > self.min_zoom:
            self.zoom_scale = max(self.zoom_scale - self.zoom_step, self.min_zoom)
            self.update_page_display()
            self.logger.info(f"ズームアウト: {self.zoom_scale:.2f}x")
    
    def reset_zoom(self):
        """ズームをリセット"""
        self.zoom_scale = 1.0
        self.update_page_display()
        self.logger.info(f"ズームリセット: {self.zoom_scale:.2f}x")

    def extract_text_items(self, text: str) -> List[str]:
        """テキストから意味のある項目を抽出"""
        # 空のテキストの場合は空リストを返却
        if not text or text.strip() == "":
            return []

        # テキストを行に分割
        lines = text.split('\n')

        # 空白行を除去
        lines = [line.strip() for line in lines if line.strip()]

        # 日付パターンを検索
        date_pattern = r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}'
        dates = []
        for line in lines:
            matches = re.findall(date_pattern, line)
            dates.extend(matches)

        # 請求書番号パターンを検索 (例: 請求書No.12345 や INV-2023-001 など)
        invoice_pattern = r'(請求書|インボイス|[Ii]nvoice)[-\s]?(No|NO|番号)?\.?\s*[\w\d\-]+'
        invoice_numbers = []
        for line in lines:
            matches = re.findall(invoice_pattern, line)
            if matches:
                # マッチした行全体を追加
                invoice_numbers.append(line)

        # 金額パターンを検索 (例: \1,234,567 や 123.45円 など)
        amount_pattern = r'(\|￥|$|＄)?\s*[\d,]+\s*(円|ドル|USD|JPY|USD|EUR|GBP|AUD|CAD|CHF|CNY|HKD|KRW|SGD|TWD)?'
        amounts = []
        for line in lines:
            if 'total' in line.lower() or 'amount' in line.lower() or '合計' in line \
                    or '金額' in line or '総額' in line:
                matches = re.findall(amount_pattern, line)
                if matches:
                    # マッチした行全体を追加
                    amounts.append(line)

        # 会社名や取引先名と思われるものを抽出 (見出し行や特定パターン)
        company_names = []
        for line in lines:
            if len(line) > 3 and ( \
                '株式会社' in line or \
                '有限会社' in line or \
                '合同会社' in line or \
                'Co., Ltd.' in line
                ):
                company_names.append(line)

        # すべての抽出項目をまとめる
        all_items = dates + invoice_numbers + amounts + company_names

        # 重複を除去して返却
        return list(set(all_items))

    def add_text_to_filename(self, item):
        """クリックされたテキストをファイル名フィールドに追加

        日付整形チェックボックスがONの場合、日付をYYYY-MM-DD形式に変換する。
        """
        if item:
            text = item.text()
            original_text = text

            # 日付整形チェックボックスの状態をログ出力
            is_format_enabled = self.format_date_checkbox.isChecked()
            self.logger.info(f"日付整形チェックボックス: {'ON' if is_format_enabled else 'OFF'}")

            # 日付整形チェックボックスがONの場合は日付を整形
            if is_format_enabled:
                text = self._format_date_string(text)

            current_text = self.rename_input.text()
            # 現在のテキストがあれば、区切り文字を追加して連結
            if current_text:
                self.rename_input.setText(f"{current_text}_{text}")
            else:
                self.rename_input.setText(text)

            if text != original_text:
                self.logger.info(f"テキスト「{original_text}」→「{text}」に変換してファイル名に追加")
            else:
                self.logger.info(f"テキスト「{text}」をファイル名に追加しました")

    def _get_default_accounts_csv_path(self) -> str:
        """デフォルトのaccounts.csvパスを取得(パッケージ内)

        Returns:
            str: デフォルトCSVファイルのパス
        """
        if getattr(sys, 'frozen', False):
            # EXE化されている場合: EXE同階層のaccounts_default.csv
            base_path = os.path.dirname(sys.executable)
            return os.path.join(base_path, 'accounts_default.csv')
        else:
            # 開発環境の場合: src/invoice_renamer/data/accounts_default.csv
            return os.path.join(
                os.path.dirname(__file__), '..', 'data', 'accounts_default.csv'
            )

    def _get_user_accounts_csv_path(self) -> str:
        """ユーザー編集可能なaccounts.csvパスを取得

        Returns:
            str: ユーザー編集用CSVファイルのパス
        """
        if getattr(sys, 'frozen', False):
            # EXE化されている場合: EXE同階層のaccounts.csv
            base_path = os.path.dirname(sys.executable)
        else:
            # 開発環境の場合: プロジェクトルートのaccounts.csv
            base_path = os.getcwd()
        return os.path.join(base_path, 'accounts.csv')

    def _load_accounts_from_file(self) -> List[str]:
        """設定ファイルから勘定科目のリストを読み込む

        EXE同階層のaccounts.csvから勘定科目を読み込む。
        ファイルが存在しない場合は、デフォルトのaccounts_default.csvからコピーして作成する。
        CSVの2列目（よみがな）でソートし、1列目（勘定科目）を返す。

        Returns:
            List[str]: よみがなでソートされた勘定科目のリスト
        """
        # ユーザー編集可能な設定ファイルのパス
        accounts_file = self._get_user_accounts_csv_path()

        # デフォルト設定ファイルのパス
        default_accounts_file = self._get_default_accounts_csv_path()

        # デフォルトの勘定科目リスト（勘定科目, よみがな）
        # ※ファイルからの読み込みに失敗した場合のフォールバック用
        default_accounts = [
            ("会議費", "かいぎひ"),
            ("外注費", "がいちゅうひ"),
            ("広告宣伝費", "こうこくせんでんひ"),
            ("交際費", "こうさいひ"),
            ("交通費", "こうつうひ"),
            ("消耗品費", "しょうもうひんひ"),
            ("水道光熱費", "すいどうこうねつひ"),
            ("地代家賃", "ちだいやちん"),
            ("通信費", "つうしんひ"),
            ("旅費交通費", "りょひこうつうひ")
        ]

        # ユーザー設定ファイルが存在しない場合は、デフォルトファイルからコピー
        if not os.path.exists(accounts_file):
            if os.path.exists(default_accounts_file):
                try:
                    shutil.copy2(default_accounts_file, accounts_file)
                    self.logger.info(f"デフォルト設定ファイルからコピーしました: {accounts_file}")
                except Exception as e:
                    self.logger.error(f"デフォルト設定ファイルのコピーに失敗: {e}")
                    # フォールバック: ハードコードされたデフォルト値でファイルを作成
                    try:
                        with open(accounts_file, 'w', encoding='utf-8', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow(["勘定科目", "よみがな"])
                            sorted_accounts = sorted(default_accounts, key=lambda x: x[1])
                            for account, yomigana in sorted_accounts:
                                writer.writerow([account, yomigana])
                        self.logger.info(f"デフォルト値で勘定科目設定ファイルを作成しました: {accounts_file}")
                    except Exception as e2:
                        self.logger.error(f"勘定科目設定ファイルの作成に失敗: {e2}")
                        sorted_accounts = sorted(default_accounts, key=lambda x: x[1])
                        return [account for account, _ in sorted_accounts]
            else:
                # デフォルトファイルも存在しない場合: ハードコードされた値でファイル作成
                try:
                    with open(accounts_file, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow(["勘定科目", "よみがな"])
                        sorted_accounts = sorted(default_accounts, key=lambda x: x[1])
                        for account, yomigana in sorted_accounts:
                            writer.writerow([account, yomigana])
                    self.logger.info(f"勘定科目設定ファイルを作成しました: {accounts_file}")
                except Exception as e:
                    self.logger.error(f"勘定科目設定ファイルの作成に失敗: {e}")
                    sorted_accounts = sorted(default_accounts, key=lambda x: x[1])
                    return [account for account, _ in sorted_accounts]

        # ファイルから勘定科目を読み込む
        try:
            with open(accounts_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                # ヘッダー行をスキップ
                next(reader, None)

                accounts_data = []
                for row in reader:
                    if len(row) >= 2 and row[0].strip():  # 勘定科目が空でない行のみ
                        account = row[0].strip()
                        yomigana = row[1].strip()
                        accounts_data.append((account, yomigana))

                if accounts_data:
                    # よみがなでソート
                    sorted_accounts = sorted(accounts_data, key=lambda x: x[1])
                    account_names = [account for account, _ in sorted_accounts]
                    self.logger.info(f"勘定科目を設定ファイルから読み込みました: {len(account_names)}項目（よみがなでソート済み）")
                    return account_names
                else:
                    self.logger.warning("勘定科目設定ファイルが空です。デフォルト値を使用します")
                    sorted_accounts = sorted(default_accounts, key=lambda x: x[1])
                    return [account for account, _ in sorted_accounts]
        except Exception as e:
            self.logger.error(f"勘定科目設定ファイルの読み込みに失敗: {e}")
            sorted_accounts = sorted(default_accounts, key=lambda x: x[1])
            return [account for account, _ in sorted_accounts]

    def add_account_to_filename(self):
        """選択された勘定科目をファイル名フィールドに追加

        ドロップダウンメニューで選択された勘定科目をファイル名に追加する。
        """
        selected_account = self.account_combo.currentText()
        if selected_account:
            current_text = self.rename_input.text()
            # 現在のテキストがあれば、区切り文字を追加して連結
            if current_text:
                self.rename_input.setText(f"{current_text}_{selected_account}")
            else:
                self.rename_input.setText(selected_account)

            self.logger.info(f"勘定科目「{selected_account}」をファイル名に追加しました")

    def _format_date_string(self, text: str) -> str:
        """テキスト内の日付をYYYY-MM-DD形式に変換

        Args:
            text (str): 変換対象のテキスト

        Returns:
            str: 日付が整形されたテキスト

        Note:
            以下の日付形式を検出して変換:
            - 令和/平成/昭和/大正/明治 N年M月D日 → YYYY-MM-DD
            - YYYY/MM/DD → YYYY-MM-DD
            - YYYY.MM.DD → YYYY-MM-DD
            - YYYY年MM月DD日 → YYYY-MM-DD
            - YY/MM/DD → 20YY-MM-DD
            - YY.MM.DD → 20YY-MM-DD
            全角・半角スペースに対応
        """
        import re
        from datetime import datetime

        self.logger.info(f"日付整形処理開始: 入力テキスト「{text}」")

        # 前処理: すべての空白文字を除去
        # Y座標許容誤差の実装により、テキスト要素間に空白が入るケースが増えたため
        # 日付パターンマッチング前に空白を除去する
        text_cleaned = re.sub(r'\s+', '', text)  # すべての空白文字を除去
        if text != text_cleaned:
            self.logger.info(f"空白文字を除去: 「{text}」 → 「{text_cleaned}」")
            text = text_cleaned

        # 全角・半角スペースの両方に対応するパターン
        space_pattern = r'[\s\u3000]*'

        # パターン0: 和暦 (例: 令和7年1月16日、令和 7年 1月16日、平成31年4月30日)
        pattern_wareki = rf'(令和|平成|昭和|大正|明治){space_pattern}(\d{{1,2}})年{space_pattern}(\d{{1,2}})月{space_pattern}(\d{{1,2}})日?'
        match = re.search(pattern_wareki, text)
        if match:
            era, year, month, day = match.groups()

            # 元号ごとの開始年（西暦）
            era_start_years = {
                '令和': 2019,  # 2019年5月1日～
                '平成': 1989,  # 1989年1月8日～2019年4月30日
                '昭和': 1926,  # 1926年12月25日～1989年1月7日
                '大正': 1912,  # 1912年7月30日～1926年12月24日
                '明治': 1868   # 1868年1月25日～1912年7月29日
            }

            # 和暦から西暦に変換
            start_year = era_start_years.get(era, 2019)
            western_year = start_year + int(year) - 1

            formatted_date = f"{western_year}-{int(month):02d}-{int(day):02d}"
            result = re.sub(pattern_wareki, formatted_date, text)
            self.logger.info(f"✓ 和暦を西暦に変換: {text} → {result} (元号: {era}{year}年)")
            return result

        # パターン1: YYYY年MM月DD日 (例: 2023年12月25日、2025年 1月16日)
        pattern1 = rf'(\d{{4}})年{space_pattern}(\d{{1,2}})月{space_pattern}(\d{{1,2}})日?'
        match = re.search(pattern1, text)
        if match:
            year, month, day = match.groups()
            formatted_date = f"{year}-{int(month):02d}-{int(day):02d}"
            result = re.sub(pattern1, formatted_date, text)
            self.logger.info(f"✓ 日付を整形: {text} → {result}")
            return result

        # パターン2: YYYY/MM/DD または YYYY.MM.DD (例: 2023/12/25, 2023.12.25)
        pattern2 = r'(\d{4})[/.](\d{1,2})[/.](\d{1,2})'
        match = re.search(pattern2, text)
        if match:
            year, month, day = match.groups()
            formatted_date = f"{year}-{int(month):02d}-{int(day):02d}"
            result = re.sub(pattern2, formatted_date, text)
            self.logger.info(f"日付を整形: {text} → {result}")
            return result

        # パターン3: YY/MM/DD または YY.MM.DD (例: 23/12/25, 23.12.25)
        # 2000年代と仮定
        pattern3 = r'(\d{2})[/.](\d{1,2})[/.](\d{1,2})'
        match = re.search(pattern3, text)
        if match:
            year, month, day = match.groups()
            full_year = f"20{year}"
            formatted_date = f"{full_year}-{int(month):02d}-{int(day):02d}"
            result = re.sub(pattern3, formatted_date, text)
            self.logger.info(f"日付を整形: {text} → {result}")
            return result

        # パターン4: YYYY-MM-DD (すでに正しい形式)
        pattern4 = r'\d{4}-\d{2}-\d{2}'
        if re.search(pattern4, text):
            self.logger.info(f"✓ 日付は既に正しい形式: {text}")
            return text

        # 日付パターンに一致しない場合はそのまま返す
        self.logger.info(f"✗ 日付パターンに一致しませんでした。元のテキストをそのまま使用: {text}")
        return text

    def update_page_display(self):
        try:
            if not self.current_pdf_path:
                return

            # プレビュー画像の取得 (PDFハンドラーに依存)
            pixmap = self.pdf_handler.get_preview(self.current_pdf_path, self.current_page)
            if pixmap:
                # ズーム倍率を適用してスケーリング
                original_size = pixmap.size()
                viewport_size = self.scroll_area.viewport().size()

                # ビューポートに収まるようにベーススケールを計算（アスペクト比を維持）
                scale_w = viewport_size.width() / original_size.width()
                scale_h = viewport_size.height() / original_size.height()
                base_scale = min(scale_w, scale_h)  # 小さい方を採用してウィンドウに収める

                # ズーム倍率を適用（zoom_scale=1.0の時はウィンドウにフィット）
                final_scale = base_scale * self.zoom_scale

                zoom_width = int(original_size.width() * final_scale)
                zoom_height = int(original_size.height() * final_scale)

                scaled_pixmap = pixmap.scaled(
                    zoom_width, zoom_height,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled_pixmap)

                # ラベルのサイズをピクセルマップのサイズに合わせる（スクロールバーが正しく表示されるように）
                self.preview_label.resize(scaled_pixmap.size())

            # テキストの取得 (PDFハンドラーに依存)
            text = self.pdf_handler.get_text(self.current_pdf_path, self.current_page)
            self.text_edit.setText(text)

            # テキストから意味のある項目を抽出してリストに表示
            self.extracted_text_items = self.extract_text_items(text)
            self.update_text_items_list()

            # ページ情報の更新（ズーム情報も含む）
            zoom_percent = int(self.zoom_scale * 100)
            self.page_label.setText(f"{self.current_page + 1}/{self.total_pages} ({zoom_percent}%)")

            # ページ切り替えボタンの有効/無効化
            self.prev_btn.setEnabled(self.current_page > 0)
            self.next_btn.setEnabled(self.current_page < self.total_pages - 1)

        except Exception as e:
            error_message = f"ページ表示時にエラーが発生しました: {str(e)}"
            self.text_edit.setText(error_message)
            self.logger.error(error_message, exc_info=True)
            QMessageBox.warning(self, "エラー", error_message)

    def update_text_items_list(self):
        """抽出されたテキスト項目をリストに表示"""
        self.text_items_list.clear()
        for item in self.extracted_text_items:
            self.text_items_list.addItem(item)

    def _normalize_filename(self, filename: str) -> str:
        """ファイル名を正規化し、Windows/macで使用できない文字を全角に変換

        Args:
            filename (str): 元のファイル名

        Returns:
            str: 正規化されたファイル名

        Note:
            以下の文字を全角に変換:
            - \\(バックスラッシュ) → ＼
            - /(スラッシュ) → ／
            - :(コロン) → ：
            - *(アスタリスク) → ＊
            - ?(クエスチョンマーク) → ？
            - "(ダブルクォート) → "
            - <(小なり) → ＜
            - >(大なり) → ＞
            - |(パイプ) → ｜
        """
        # Windows/macで使用できない文字を全角に変換
        char_map = {
            '\\': '＼',
            '/': '／',
            ':': '：',
            '*': '＊',
            '?': '？',
            '"': '"',
            '<': '＜',
            '>': '＞',
            '|': '｜'
        }

        normalized = filename
        for half_char, full_char in char_map.items():
            normalized = normalized.replace(half_char, full_char)

        # 先頭と末尾の空白を削除
        normalized = normalized.strip()

        # 先頭と末尾のピリオド（.）を削除（Windowsで問題になる）
        normalized = normalized.strip('.')

        return normalized

    def reset_filename(self):
        """新しいファイル名を変更前のファイル名に戻す

        変更前ファイル名の値を新しいファイル名のフィールドに設定する。
        """
        original_filename = self.original_filename_value.text()
        if original_filename:
            self.rename_input.setText(original_filename)
            self.logger.info(f"ファイル名を元に戻しました: {original_filename}")
        else:
            self.logger.warning("変更前ファイル名が設定されていません")

    def rename_current_file(self):
        """現在開いているPDFファイルをリネームして移動

        処理フロー:
        1. PDFファイルとフォルダの存在確認
        2. originalフォルダとrenamedフォルダを作成（存在しない場合）
        3. 新しいファイル名の重複をチェック
        4. 元のファイルをoriginalフォルダに移動
        5. リネームしたファイルをrenamedフォルダに作成
        6. PDF一覧を再取得

        Note:
            元のファイルはoriginalフォルダに移動し、リネームしたファイルはrenamedフォルダに作成する方式
        """
        if not self.current_pdf_path:
            QMessageBox.warning(self, "エラー", "PDFファイルが開かれていません")
            return

        # PDFファイルの存在確認
        if not os.path.exists(self.current_pdf_path):
            QMessageBox.warning(
                self,
                "エラー",
                f"PDFファイルが見つかりません。\n"
                f"ファイルが移動または削除された可能性があります。\n\n"
                f"ファイルパス: {self.current_pdf_path}"
            )
            self.logger.error(f"PDFファイルが存在しません: {self.current_pdf_path}")
            return

        # PDFフォルダの存在確認
        if not self.current_folder or not os.path.exists(self.current_folder):
            QMessageBox.warning(
                self,
                "エラー",
                f"PDFフォルダが見つかりません。\n"
                f"フォルダが移動または削除された可能性があります。\n\n"
                f"フォルダパス: {self.current_folder if self.current_folder else '未設定'}"
            )
            self.logger.error(f"PDFフォルダが存在しません: {self.current_folder}")
            return

        new_name = self.rename_input.text().strip()

        if not new_name:
            QMessageBox.warning(self, "エラー", "新しいファイル名を入力してください")
            return

        # .pdf拡張子を一旦除去（正規化のため）
        if new_name.lower().endswith('.pdf'):
            new_name_base = new_name[:-4]
        else:
            new_name_base = new_name

        # ファイル名を正規化（不適切な文字を全角に変換）
        normalized_name_base = self._normalize_filename(new_name_base)

        # 正規化後のファイル名が空でないかチェック
        if not normalized_name_base:
            QMessageBox.warning(self, "エラー", "有効なファイル名を入力してください")
            return

        # 正規化前後で変更があった場合は通知
        if normalized_name_base != new_name_base:
            replaced_chars = []
            for half_char, full_char in {
                '\\': '＼', '/': '／', ':': '：', '*': '＊',
                '?': '？', '"': '"', '<': '＜', '>': '＞', '|': '｜'
            }.items():
                if half_char in new_name_base:
                    replaced_chars.append(f"{half_char} → {full_char}")

            message = f"ファイル名に使用できない文字が含まれていたため、以下のように変換されました:\n\n"
            if replaced_chars:
                message += "\n".join(replaced_chars) + "\n\n"
            message += f"変換前: {new_name_base}\n変換後: {normalized_name_base}\n\nこのまま続行しますか？"

            reply = QMessageBox.question(
                self,
                "ファイル名の自動変換",
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.No:
                self.logger.info("ユーザーがファイル名変換をキャンセルしました")
                return

            self.logger.info(f"ファイル名を正規化: {new_name_base} → {normalized_name_base}")

        # .pdf拡張子を追加
        new_name = normalized_name_base + '.pdf'

        # 元のファイル名と比較
        original_filename = os.path.basename(self.current_pdf_path)
        if new_name == original_filename:
            QMessageBox.warning(self, "エラー", "ファイル名が変更されていません。")
            self.logger.warning(f"ファイル名が変更されていないため処理を中止: {new_name}")
            return

        try:
            # 1. originalフォルダとrenamedフォルダのパスを作成
            original_folder = os.path.join(self.current_folder, 'original')
            renamed_folder = os.path.join(self.current_folder, 'renamed')

            # フォルダが存在しない場合は作成
            if not os.path.exists(original_folder):
                os.makedirs(original_folder)
                self.logger.info(f"originalフォルダを作成しました: {original_folder}")

            if not os.path.exists(renamed_folder):
                os.makedirs(renamed_folder)
                self.logger.info(f"renamedフォルダを作成しました: {renamed_folder}")

            # 2. 新しいファイルパスを作成
            new_file_path = os.path.join(renamed_folder, new_name)

            # 3. 同名ファイルの存在チェック
            if os.path.exists(new_file_path):
                QMessageBox.warning(
                    self,
                    "ファイル名の重複",
                    f"renamed フォルダ内に同じ名前のファイルが既に存在します:\n{new_name}\n\n"
                    "別のファイル名を指定してください。"
                )
                self.logger.warning(f"ファイル名が重複しているため処理を中止: {new_name}")
                return

            # 4. 元のファイル名を取得
            original_filename = os.path.basename(self.current_pdf_path)
            original_file_new_path = os.path.join(original_folder, original_filename)

            # originalフォルダ内に同名ファイルが既に存在する場合
            if os.path.exists(original_file_new_path):
                # タイムスタンプ付きのファイル名を生成
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_without_ext = original_filename[:-4] if original_filename.lower().endswith('.pdf') else original_filename
                original_file_new_path = os.path.join(original_folder, f"{name_without_ext}_{timestamp}.pdf")
                self.logger.info(f"同名ファイルが存在するため、タイムスタンプを追加: {os.path.basename(original_file_new_path)}")

            # 5. 元のファイルのタイムスタンプを取得
            stat_info = os.stat(self.current_pdf_path)
            original_atime = stat_info.st_atime  # アクセス時刻
            original_mtime = stat_info.st_mtime  # 変更時刻

            # 6. リネームしたファイルをrenamedフォルダに複製
            import shutil
            shutil.copy2(self.current_pdf_path, new_file_path)

            # タイムスタンプを復元（copy2で保持されるが念のため）
            os.utime(new_file_path, (original_atime, original_mtime))

            self.logger.info(f"ファイルをリネームしてrenamedフォルダに複製: {original_filename} -> renamed/{new_name}")

            # 7. 開いているPDFをクローズ（ファイルハンドルを解放）
            if self.pdf_handler:
                self.pdf_handler.close()
                self.logger.info(f"PDFをクローズしました: {original_filename}")

            # 8. 元のファイルをoriginalフォルダに移動
            shutil.move(self.current_pdf_path, original_file_new_path)
            self.logger.info(f"元のファイルを移動: {original_filename} -> original/{os.path.basename(original_file_new_path)}")

            # 9. PDF一覧を再取得
            self.load_pdf_files(self.current_folder)

            # 成功メッセージを表示
            QMessageBox.information(
                self,
                "完了",
                f"ファイルをリネームしました:\n\n"
                f"元のファイル: {original_filename}\n"
                f"→ original/{os.path.basename(original_file_new_path)}\n\n"
                f"リネーム後: {new_name}\n"
                f"→ renamed/{new_name}"
            )

            # UIの状態を更新
            self.rename_input.clear()
            self.current_pdf_path = None
            self.preview_label.clear()
            self.preview_label.setText("PDFファイルを選択してください")

        except PermissionError as e:
            error_message = f"ファイルへのアクセス権限がありません:\n{str(e)}"
            self.logger.error(error_message, exc_info=True)
            QMessageBox.warning(self, "権限エラー", error_message)

        except IOError as e:
            error_message = f"ファイルの複製中にエラーが発生しました:\n{str(e)}"
            self.logger.error(error_message, exc_info=True)
            QMessageBox.warning(self, "I/Oエラー", error_message)

        except Exception as e:
            error_message = f"ファイル処理中に予期しないエラーが発生しました:\n{str(e)}"
            self.logger.error(error_message, exc_info=True)
            QMessageBox.warning(self, "エラー", error_message)

    # def _initialize_pdf_handler(self) -> Optional[PDFHandler]:
    #     """設定に基づいてPDFハンドラーの初期化"""
    #     handler_type = self.config.get_pdf_handler()

    #     try:
    #         if handler_type.lower() == 'pymypdf':
    #             self.logger.info("PyMuPDFハンドラを初期化します。")
    #             return PyMuPDFHandler()
    #         elif handler_type.lower = 'pdf2image':
    #             self.logger.info("PDF2Imageハンドラを初期化します")
    #             return PDF2ImageHandler()
    #         else:
    #             self.logger.error(f"未知のPDFハンドラが指定されています: {handler_type}")
    #         return None
    #     except Exception as e:
    #         self.logger.error(f"PDFハンドラの初期化に失敗しました: {str(e)}")
    #         return None

    def setup_ui(self):
        self.setWindowTitle("PDF Viewer")
        self.resize(1200, 800)
        self.current_folder = None

        # 中央ウィジェットと全体レイアウト
        central_widget = QWidget()
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # 左サイドバー（ボタンとPDF一覧）
        sidebar_layout = QVBoxLayout()
        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar_layout)
        sidebar_widget.setMaximumWidth(300)

        # PDF一覧ウィジェット
        self.pdf_list_widget = QListWidget()
        sidebar_layout.addWidget(self.pdf_list_widget)

        # PDFフォルダ選択ボタン
        self.select_folder_btn = QPushButton(constants.BTN_CHOOSE_PDF_FOLDER)
        sidebar_layout.addWidget(self.select_folder_btn)

        # 抽出テキストアイテムリストを追加
        text_items_label = QLabel("抽出されたテキスト")
        sidebar_layout.addWidget(text_items_label)
        self.text_items_list = QListWidget()
        sidebar_layout.addWidget(self.text_items_list)

        # 勘定科目選択UI（ドロップダウンメニュー、ラベル、ボタン）
        account_layout = QHBoxLayout()

        # 勘定科目ラベル
        account_label = QLabel("勘定科目：")
        account_layout.addWidget(account_label)

        # 勘定科目ドロップダウンメニュー
        self.account_combo = QComboBox()
        # 設定ファイルから勘定科目を読み込んで追加
        accounts = self._load_accounts_from_file()
        self.account_combo.addItems(accounts)
        account_layout.addWidget(self.account_combo)

        # 追加ボタン
        self.add_account_btn = QPushButton("追加")
        self.add_account_btn.clicked.connect(self.add_account_to_filename)
        account_layout.addWidget(self.add_account_btn)

        sidebar_layout.addLayout(account_layout)

        # 日付整形チェックボックスを追加
        self.format_date_checkbox = QCheckBox("📅 日付を整形して適用")
        self.format_date_checkbox.setChecked(True)  # デフォルトはON
        self.format_date_checkbox.setStyleSheet(
            "QCheckBox { "
            "color: #555; "
            "font-size: 11px; "
            "padding: 5px; "
            "} "
            "QCheckBox::indicator:checked { "
            "background-color: #007ACC; "
            "border: 1px solid #005a9e; "
            "}"
        )
        sidebar_layout.addWidget(self.format_date_checkbox)

        # デバッグモード切り替えチェックボックスを追加
        self.debug_checkbox = QCheckBox("🔧 デバッグモード（詳細診断情報表示）")
        self.debug_checkbox.setChecked(self.debug_mode)
        self.debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
        
        # OCR言語選択コンボボックスを追加
        self.language_label = QLabel("🌌 OCR言語:")
        self.language_combo = QComboBox()
        self.language_combo.addItems([
            "🇯🇵 日本語優先 (jpn+eng)",
            "🇺🇸 英語のみ (eng)",
            "🇯🇵 日本語のみ (jpn)",
            "🌐 自動検出"
        ])
        self.language_combo.setCurrentIndex(0)  # デフォルトは日本語優先
        self.ocr_language = 'jpn+eng'
        self.debug_checkbox.setStyleSheet(
            "QCheckBox { "
            "color: #555; "
            "font-size: 11px; "
            "} "
            "QCheckBox::indicator:checked { "
            "background-color: #007ACC; "
            "border: 1px solid #005a9e; "
            "}"
        )
        sidebar_layout.addWidget(self.debug_checkbox)
        
        # OCR言語選択のスタイル設定
        self.language_label.setStyleSheet(
            "QLabel { "
            "color: #555; "
            "font-size: 11px; "
            "margin-top: 10px; "
            "}"
        )
        self.language_combo.setStyleSheet(
            "QComboBox { "
            "padding: 5px; "
            "border: 1px solid #ccc; "
            "border-radius: 3px; "
            "background-color: white; "
            "color: #333; "
            "font-size: 11px; "
            "} "
            "QComboBox::drop-down { "
            "border: none; "
            "} "
            "QComboBox::down-arrow { "
            "image: none; "
            "border-style: solid; "
            "border-width: 3px; "
            "border-color: transparent transparent #666 transparent; "
            "} "
            "QComboBox QAbstractItemView { "
            "background-color: white; "
            "border: 1px solid #ccc; "
            "selection-background-color: #0078d4; "
            "selection-color: white; "
            "color: #333; "
            "} "
            "QComboBox:hover { "
            "border-color: #0078d4; "
            "} "
            "QComboBox:focus { "
            "border-color: #0078d4; "
            "outline: none; "
            "}"
        )
        sidebar_layout.addWidget(self.language_label)
        sidebar_layout.addWidget(self.language_combo)
        
        # レイアウトに追加
        main_layout.addWidget(sidebar_widget)

        # 中央のプレビューエリアとコントロール
        center_layout = QVBoxLayout()
        center_widget = QWidget()
        center_widget.setLayout(center_layout)

        # プレビュー画像表示用ラベル（範囲選択可能）をスクロールエリアに配置
        self.preview_label = SelectableLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(800, 600) # プレビューの最小サイズ

        # スクロールエリアを作成してpreview_labelを配置
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.preview_label)
        self.scroll_area.setWidgetResizable(False)  # ズーム時に自動リサイズしない
        self.scroll_area.setAlignment(Qt.AlignCenter)

        # SelectableLabelにスクロールエリアへの参照を設定（パンニング用）
        self.preview_label.scroll_area = self.scroll_area

        center_layout.addWidget(self.scroll_area)

        # ページ制御エリア
        control_layout = QHBoxLayout()
        
        # ページ遷移コントロール
        self.prev_btn = QPushButton("< 前")
        self.next_btn = QPushButton("次 >")
        self.page_label = QLabel("1/1")
        control_layout.addWidget(self.prev_btn)
        control_layout.addWidget(self.page_label)
        control_layout.addWidget(self.next_btn)
        
        # セパレーター
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        control_layout.addWidget(separator)
        
        # ズームコントロール
        zoom_label = QLabel("🔍 ズーム:")
        self.zoom_out_btn = QPushButton("-")
        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_in_btn = QPushButton("+")
        
        # ズームボタンのサイズ調整
        for btn in [self.zoom_out_btn, self.zoom_in_btn]:
            btn.setMaximumWidth(30)
        self.zoom_reset_btn.setMaximumWidth(50)
        
        control_layout.addWidget(zoom_label)
        control_layout.addWidget(self.zoom_out_btn)
        control_layout.addWidget(self.zoom_reset_btn)
        control_layout.addWidget(self.zoom_in_btn)
        
        # コントロール情報ラベル
        self.control_info_label = QLabel("Ctrl+ホイールでズーム")
        self.control_info_label.setStyleSheet("color: #666; font-size: 10px;")
        control_layout.addWidget(self.control_info_label)

        # ファイル名変更フィールド
        rename_container = QVBoxLayout()

        # 変更前ファイル名の表示
        original_filename_layout = QHBoxLayout()
        original_filename_label = QLabel("変更前ファイル名")
        self.original_filename_value = QLabel("")
        self.original_filename_value.setStyleSheet(
            "QLabel { "
            "color: #333; "
            "background-color: #d0d0d0; "
            "padding: 5px; "
            "border: 1px solid #ccc; "
            "border-radius: 3px; "
            "}"
        )
        original_filename_layout.addWidget(original_filename_label)
        original_filename_layout.addWidget(self.original_filename_value, 1)

        # 元に戻すボタン
        self.reset_filename_btn = QPushButton("元に戻す")
        self.reset_filename_btn.setFixedWidth(80)
        original_filename_layout.addWidget(self.reset_filename_btn)

        # 新しいファイル名の入力
        rename_layout = QHBoxLayout()
        rename_label = QLabel("新しいファイル名")
        self.rename_input = QLineEdit()
        self.rename_btn = QPushButton("名前変更")
        rename_layout.addWidget(rename_label)
        rename_layout.addWidget(self.rename_input)
        rename_layout.addWidget(self.rename_btn)

        # レイアウトをコンテナに追加
        rename_container.addLayout(original_filename_layout)
        rename_container.addLayout(rename_layout)

        # コントロールをレイアウトに追加
        control_widget = QWidget()
        control_container = QVBoxLayout()
        control_container.addLayout(control_layout)
        control_container.addLayout(rename_container)
        control_widget.setLayout(control_container)
        center_layout.addWidget(control_widget)

        # 中央ウィジェットをメインレイアウトに追加
        main_layout.addWidget(center_widget)

        # 右側のテキスト表示エリア（デフォルトで非表示）
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMinimumWidth(300)
        self.text_edit.setVisible(False)  # 非表示にして他のパーツが広く使えるように
        main_layout.addWidget(self.text_edit)
    
    def on_selection_made(self, selection_rect: QRect):
        """範囲選択が行われた時の処理（非同期）"""
        if not self.current_pdf_path:
            return
        
        # 既に分析中の場合は新しい分析をキャンセル
        if self.analysis_in_progress and self.analysis_worker:
            self.analysis_worker.terminate()
            self.analysis_worker.wait()
        
        try:
            # 既存のバブルを削除
            self._clear_bubbles()
            
            # 処理中表示
            self._show_processing_indicator(selection_rect)
            
            # 選択データを作成（ズーム座標をそのまま使用）
            # 座標変換はselection_analyzerで実行される
            selection_data = SelectionData(
                rect=selection_rect,
                page_number=self.current_page,
                pdf_path=self.current_pdf_path
            )
            
            # デバッグ情報をログ出力
            preview_size = (self.preview_label.width(), self.preview_label.height())
            quick_mode = not self.debug_mode  # デバッグモードでは詳細分析、通常は高速モード
            
            # デバッグモードの状態を常にログ出力
            self.logger.info(f"🔧 分析モード: {'デバッグ' if self.debug_mode else '通常'} (quick_mode={quick_mode})")
            
            if self.debug_mode:
                self.logger.info(f"選択範囲分析開始 - Qt座標: x={selection_rect.x()}, y={selection_rect.y()}, w={selection_rect.width()}, h={selection_rect.height()}")
                self.logger.info(f"ズーム倍率: {self.zoom_scale:.3f}")
                self.logger.info(f"プレビューサイズ: {preview_size}")
            
            # 非同期で分析を実行
            analysis_params = {
                'zoom_scale': self.zoom_scale,
                'preview_size': preview_size,
                'ocr_language': self.get_ocr_language()
            }
            self.analysis_worker = AnalysisWorker(self.selection_analyzer, selection_data, analysis_params, quick_mode)
            self.analysis_worker.analysis_finished.connect(self.on_analysis_finished)
            self.analysis_worker.analysis_error.connect(self.on_analysis_error)
            self.analysis_worker.finished.connect(self.on_worker_finished)
            
            self.analysis_in_progress = True
            self.analysis_worker.start()
            
            self.logger.info(f"範囲選択分析を開始: {selection_rect.x()},{selection_rect.y()},{selection_rect.width()},{selection_rect.height()}")
            
        except Exception as e:
            error_msg = f"範囲選択分析開始エラー: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            QMessageBox.warning(self, "エラー", error_msg)
    
    def on_selection_cleared(self):
        """選択範囲がクリアされた時の処理"""
        # 分析中の処理をキャンセル
        if self.analysis_in_progress and self.analysis_worker:
            self.analysis_worker.terminate()
            self.analysis_worker.wait()
            self.analysis_in_progress = False
        
        # バブルを削除
        self._clear_bubbles()
        
        self.logger.info("選択範囲がクリアされました")
    
    def on_analysis_finished(self, analysis_results):
        """分析完了時の処理"""
        try:
            if analysis_results:
                # 詳細分析情報を取得
                detailed_analysis = self.selection_analyzer.get_detailed_analysis(analysis_results)

                # バブルに表示するテキストを作成
                bubble_text = self._create_bubble_text(detailed_analysis)

                # 抽出されたテキストを取得（通常モードでのコピー用）
                extracted_text = detailed_analysis.get('combined_text', '')

                # バブルを表示（processing indicatorを削除してから）
                self._clear_bubbles()
                self._show_analysis_bubble(bubble_text, self.last_selection_rect, extracted_text)

                # 抽出されたテキストを左下のリストに追加
                if extracted_text and extracted_text.strip() and "【診断情報】" not in extracted_text:
                    # テキストが有効な場合のみリストに追加
                    self._add_extracted_text_to_list(extracted_text)

                # ログに記録
                self.logger.info(f"範囲選択分析完了: {len(analysis_results)}個の要素を検出")
            else:
                self.logger.warning("選択範囲内に解析可能な要素が見つかりませんでした")
                
        except Exception as e:
            error_msg = f"分析結果処理エラー: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
    
    def on_analysis_error(self, error_msg):
        """分析エラー時の処理"""
        self._clear_bubbles()
        self.logger.error(f"範囲選択分析エラー: {error_msg}")
        QMessageBox.warning(self, "分析エラー", f"範囲選択の分析中にエラーが発生しました:\n{error_msg}")
    
    def on_worker_finished(self):
        """ワーカー終了時の処理"""
        self.analysis_in_progress = False
        self.analysis_worker = None
    
    def _show_processing_indicator(self, selection_rect: QRect):
        """処理中インジケーターを表示"""
        self.last_selection_rect = selection_rect  # 後で使用するために保存
        
        # 簡単な処理中メッセージを表示
        processing_text = "🔄 分析中...\n選択範囲を解析しています。\nしばらくお待ちください。"
        
        # バブルの位置を計算
        global_pos = self.preview_label.mapToGlobal(
            QPoint(selection_rect.right() + 10, selection_rect.top())
        )
        
        # 処理中バブルを作成して表示
        processing_bubble = AnalysisResultBubble(processing_text, global_pos, False, None, self)
        processing_bubble.show()
        self.current_bubbles.append(processing_bubble)
    
    def toggle_debug_mode(self, state):
        """デバッグモードの切り替え"""
        # stateが2の場合はチェック状態、0の場合はアンチェック状態
        self.debug_mode = state == 2
        self.logger.info(f"🔧 デバッグモード切り替え: {'有効' if self.debug_mode else '無効'} (state={state})")
    
    def get_ocr_language(self) -> str:
        """選択されたOCR言語を取得"""
        index = self.language_combo.currentIndex()
        language_map = {
            0: 'jpn+eng',  # 日本語優先
            1: 'eng',      # 英語のみ
            2: 'jpn',      # 日本語のみ
            3: 'auto'      # 自動検出
        }
        return language_map.get(index, 'jpn+eng')
    
    def _create_bubble_text(self, analysis: dict) -> str:
        """分析結果からバブル表示用のテキストを作成"""
        if self.debug_mode:
            return self._create_debug_bubble_text(analysis)
        else:
            return self._create_normal_bubble_text(analysis)
    
    def _create_normal_bubble_text(self, analysis: dict) -> str:
        """通常モード用のシンプルなバブルテキスト"""
        text_parts = []
        
        # 抽出されたテキストのみを表示
        combined_text = analysis['combined_text']
        if combined_text and combined_text.strip():
            # 診断情報は除外し、実際の抽出テキストのみ表示
            if "【診断情報】" not in combined_text:
                text_parts.append("📄 抽出されたテキスト:")
                text_parts.append("")
                text_parts.append(combined_text)
            else:
                text_parts.append("❌ テキストを抽出できませんでした")
                text_parts.append("")
                text_parts.append("💡 デバッグモードで詳細を確認できます")
        else:
            text_parts.append("❌ テキストが検出されませんでした")
            text_parts.append("")
            text_parts.append("💡 以下をお試しください:")
            text_parts.append("  • 画像全体を選択する")
            text_parts.append("  • より大きな範囲を選択する")
            text_parts.append("  • デバッグモードで詳細確認")
        
        # 基本統計（簡略版）
        if analysis['total_elements'] > 0:
            text_parts.append("")
            text_parts.append(f"📊 要素: {analysis['text_elements']}テキスト + {analysis['image_elements']}画像")
            if analysis['average_confidence'] > 0:
                text_parts.append(f"🎯 信頼度: {analysis['average_confidence']:.0%}")
        
        return "\n".join(text_parts)
    
    def _create_debug_bubble_text(self, analysis: dict) -> str:
        """デバッグモード用の詳細なバブルテキスト"""
        text_parts = []
        
        # ヘッダー
        text_parts.append("🔧 詳細診断情報 (v6)")
        text_parts.append("=" * 40)
        
        # 統計情報
        text_parts.append("📊 統計情報:")
        text_parts.append(f"  • 総要素数: {analysis['total_elements']}")
        text_parts.append(f"  • テキスト要素: {analysis['text_elements']}個")
        text_parts.append(f"  • 画像要素: {analysis['image_elements']}個")
        
        # エラー要素があれば表示
        if analysis.get('error_elements', 0) > 0:
            text_parts.append(f"  • エラー/診断要素: {analysis['error_elements']}個")
        
        text_parts.append(f"  • 平均信頼度: {analysis['average_confidence']:.1%}")
        text_parts.append("")
        
        # 抽出されたテキスト
        combined_text = analysis['combined_text']
        text_parts.append("📄 抽出結果:")
        if combined_text and combined_text.strip():
            # 診断情報と実際のテキストを分けて表示
            if "【診断情報】" in combined_text:
                text_parts.append("  ℹ️ 診断モード - 詳細情報のみ")
                text_parts.append(combined_text)
            else:
                text_parts.append("  ✅ 選択範囲からテキストを抽出:")
                text_parts.append(f"  '{combined_text}'")
        else:
            text_parts.append("  ❌ テキストが検出されませんでした")
        
        text_parts.append("")
        
        # 詳細情報
        if analysis.get('details'):
            text_parts.append("🔍 要素詳細:")
            for i, detail in enumerate(analysis['details'][:5]):  # 最初の5つまで表示
                element_type = detail['type']
                detail_text = detail['text']
                
                # 処理方法の情報を抽出
                processing_method = "不明"
                if "直接レンダリング" in detail_text:
                    processing_method = "直接レンダリング"
                elif "cropped_from_existing" in detail_text:
                    processing_method = "既存画像切り抜き"
                elif "診断情報" in detail_text:
                    processing_method = "診断情報"
                elif element_type == "text":
                    processing_method = "PDFテキスト抽出"
                
                element_info = f"  {i+1}. [{element_type}] 方法: {processing_method}"
                text_parts.append(element_info)
                
                # テキスト内容（長すぎる場合は省略）
                display_text = detail_text[:60] if detail_text else ""
                if len(detail_text) > 60:
                    display_text += "..."
                text_parts.append(f"     内容: {display_text}")
                
                # 信頼度と座標
                text_parts.append(f"     信頼度: {detail['confidence']:.1%}")
                bbox = detail['bbox']
                text_parts.append(f"     座標: ({bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f})")
                
                text_parts.append("")
        
        # v6の改善点説明
        text_parts.append("🆕 v6改善点:")
        text_parts.append("  • 選択範囲の直接レンダリング実装")
        text_parts.append("  • 既存画像の正確な切り抜き")
        text_parts.append("  • ページ全体フォールバック廃止")
        text_parts.append("  • 座標変換精度向上")
        
        return "\n".join(text_parts)
    
    def _show_analysis_bubble(self, text: str, selection_rect: QRect, extracted_text: str = None):
        """分析結果のバブルを表示

        Args:
            text (str): 表示するテキスト
            selection_rect (QRect): 選択範囲の矩形
            extracted_text (str): 抽出されたテキスト（通常モードでのコピー用）
        """
        # 既存のバブルを削除
        self._clear_bubbles()

        # バブルの位置を計算（選択範囲の右上に表示）
        global_pos = self.preview_label.mapToGlobal(
            QPoint(selection_rect.right() + 10, selection_rect.top())
        )

        # 新しいバブルを作成して表示
        bubble = AnalysisResultBubble(text, global_pos, self.debug_mode, extracted_text, self)
        bubble.show()
        self.current_bubbles.append(bubble)
    
    def _clear_bubbles(self):
        """表示中のバブルをすべて削除"""
        for bubble in self.current_bubbles:
            bubble.hide()
            bubble.deleteLater()
        self.current_bubbles.clear()

    def _add_extracted_text_to_list(self, text: str):
        """抽出されたテキストを左下のリストに追加

        Args:
            text (str): 抽出されたテキスト

        Note:
            テキストを行ごとに分割し、空でない行のみをリストに追加。
            既に存在するテキストは重複して追加しない。
        """
        if not text or not text.strip():
            return

        # テキストを行に分割
        lines = text.split('\n')

        # 各行を処理してリストに追加
        for line in lines:
            line = line.strip()
            if line:  # 空でない行のみ
                # 既に同じテキストがリストにあるかチェック
                exists = False
                for i in range(self.text_items_list.count()):
                    if self.text_items_list.item(i).text() == line:
                        exists = True
                        break

                # 重複していなければ追加
                if not exists:
                    item = QListWidgetItem(line)
                    self.text_items_list.addItem(item)
                    self.logger.info(f"抽出テキストをリストに追加: {line[:50]}...")

    def open_pdf(self, item):
        """ PDFファイルを開いてプレビューとテキストを表示 """
        if not self.current_folder:
            return

        try:
            self.current_pdf_path = os.path.join(self.current_folder, item.text())
            self.logger.info(f"PDFファイルを開きます: {item.text()}")

            # エラーハンドリングは pdf_handler.load_pdf 内で実行される
            if self.pdf_handler.load_pdf(self.current_pdf_path, parent_widget=self):
                self.current_page = 0
                self.total_pages = self.pdf_handler.get_page_count()

                # ズームと表示位置をリセット
                self.reset_zoom()

                # 新しいファイル名フィールドは空のまま（ユーザーが入力）
                self.rename_input.clear()
                # 変更前ファイル名ラベルを更新
                self.original_filename_value.setText(item.text())
                self.logger.info(f"PDFファイルが正常に開かれました: {item.text()}")
            else:
                # load_pdfでエラーハンドリング済みなので、UIの状態をリセット
                self.text_edit.setText("PDFファイルの読み込みに失敗しました")
                self.current_pdf_path = None
                self.current_page = 0
                self.total_pages = 0

        except Exception as e:
            # 予期しないエラーの場合
            self.error_handler.handle_error(
                e, 
                ErrorType.UNKNOWN_ERROR, 
                parent=self,
                additional_info=f"ファイル: {item.text()}"
            )
            # UIの状態をリセット
            self.text_edit.setText("予期しないエラーが発生しました")
            self.current_pdf_path = None
            self.current_page = 0
            self.total_pages = 0

    def select_pdf_folder(self):
        """PDFフォルダ選択ダイアログを表示（OSネイティブUI使用）

        Windows/MacのネイティブなファイルダイアログUIを使用します。
        前回選択したフォルダを記憶し、次回起動時もそこから開始します。

        以下の機能が利用可能:
        - OSの標準的な見た目と操作性
        - 検索機能
        - クイックアクセス（よく使うフォルダ）
        - ドキュメント、ダウンロードなどの標準フォルダへのショートカット
        - Look in: フィールドの直接編集（パス入力）
        - お気に入り登録
        - 履歴機能

        Note:
            選択したフォルダパスは settings.ini に保存されます。
            settings.ini はプロジェクトルートに作成され、.gitignore で除外されます。
            読み込み時はバリデーションが行われ、不正な値は無視されます。
        """
        # 初期ディレクトリを設定（前回選択したフォルダがあればそこから、なければデフォルト位置）
        initial_dir = self.current_folder if self.current_folder else ""

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "PDFフォルダを選択",
            initial_dir,
            QFileDialog.ShowDirsOnly
        )

        if folder_path:
            self.current_folder = folder_path
            # フォルダパスを永続化（次回起動時も復元される）
            self.settings.setValue("last_folder_path", folder_path)
            self.load_pdf_files(folder_path)
            self.logger.info(f"PDFフォルダを選択: {folder_path}")

    def load_pdf_files(self, folder_path):
        # PDFファイルのみを抽出してリスト化
        pdf_files = [f for f in os.listdir(folder_path)
                     if f.lower().endswith('.pdf')]

        # リストウィジェットを更新
        self.pdf_list_widget.clear()
        for pdf in pdf_files:
            self.pdf_list_widget.addItem(pdf)



