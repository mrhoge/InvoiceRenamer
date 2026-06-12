"""
選択範囲分析モジュール (v6)

PDFビューアー上でユーザーが選択した範囲内のテキストや画像を分析し、
OCR処理を含む高度な情報抽出を行う。

主な機能:
- Qt座標からPDF座標への変換（ズーム対応）
- テキスト要素の抽出と分析
- 画像要素の抽出とOCR処理
- 読み順の自動判定
- メモリ効率を考慮した高速モード

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
from PySide6.QtCore import QRect
from invoice_renamer.utils.logger import setup_logger
from invoice_renamer.utils.error_handler import ErrorHandler, ErrorType
from invoice_renamer.logic.config_manager import ConfigManager
from invoice_renamer.logic.ocr_preprocess import preprocess_variants


@dataclass
class AnalysisResult:
    """分析結果を格納するデータクラス

    Attributes:
        text (str): 抽出されたテキスト
        element_type (str): 要素タイプ ('text', 'image', 'mixed', 'diagnostic', 'error')
        confidence (float): OCR信頼度（0.0〜1.0）
        bbox (Tuple[float, float, float, float]): バウンディングボックス (x0, y0, x1, y1)
        reading_order (int): 読み順（上から左から順に番号付け）
    """
    text: str
    element_type: str  # 'text', 'image', 'mixed'
    confidence: float
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    reading_order: int


@dataclass
class SelectionData:
    """選択範囲情報を格納するデータクラス

    Attributes:
        rect (QRect): Qt座標系での選択矩形
        page_number (int): PDFのページ番号（0から始まる）
        pdf_path (str): PDFファイルのパス
    """
    rect: QRect
    page_number: int
    pdf_path: str


class SelectionAnalyzer:
    """PDF内の選択範囲を分析するクラス

    PDFビューアーで選択された範囲内のテキストと画像を抽出・分析する。
    ズーム対応の座標変換、OCR処理、読み順判定などの機能を提供。

    Attributes:
        logger: ロガーインスタンス
        error_handler (ErrorHandler): エラーハンドラーインスタンス
        config_manager (ConfigManager): 設定管理インスタンス
    """

    def __init__(self):
        self.logger = setup_logger('invoice_renamer.selection_analyzer')
        self.error_handler = ErrorHandler(self.logger)
        self.config_manager = ConfigManager()
        
    def analyze_selection(self, selection: SelectionData, analysis_params: dict = None, quick_mode: bool = False) -> List[AnalysisResult]:
        """
        選択範囲内の要素を分析し、結果を返す
        
        Args:
            selection (SelectionData): 選択範囲情報
            analysis_params (dict): 分析パラメータ (zoom_scale, preview_size等)
            quick_mode (bool): 高速モード（詳細ログを省略）
            
        Returns:
            List[AnalysisResult]: 分析結果のリスト
        """
        try:
            # メモリ使用量チェック
            if not self._check_memory_usage():
                self.logger.warning("メモリ使用率が高いため、高速モードに切り替えます")
                quick_mode = True
            
            doc = fitz.open(selection.pdf_path)
            page = doc[selection.page_number]
            
            # 分析パラメータから情報を取得
            if analysis_params is None:
                analysis_params = {}
            zoom_scale = analysis_params.get('zoom_scale', 1.0)
            preview_size = analysis_params.get('preview_size', (800, 600))
            ocr_language = analysis_params.get('ocr_language', 'jpn+eng')
            
            # 分析モードの状態を常にログ出力
            self.logger.info(f"🔍 SelectionAnalyzer - 分析モード: {'詳細' if not quick_mode else '高速'} (quick_mode={quick_mode})")
            
            # Qt座標をPDF座標に変換（ズームを考慮）
            pdf_rect = self._convert_qt_to_pdf_coords_with_zoom(selection.rect, page, zoom_scale, preview_size, quick_mode)
            
            if not quick_mode:
                # 詳細な診断情報を出力（詳細モードのみ）
                self.logger.info("=" * 60)
                self.logger.info(f"選択範囲分析開始（詳細モード）")
                self.logger.info(f"Qt選択範囲: x={selection.rect.x()}, y={selection.rect.y()}, w={selection.rect.width()}, h={selection.rect.height()}")
                self.logger.info(f"プレビューサイズ: {preview_size}")
                self.logger.info(f"PDF範囲: {pdf_rect}")
                self.logger.info(f"ページサイズ: {page.rect}")
            
            # 選択範囲内の要素を取得（高速モード対応）
            text_elements = self._extract_text_elements(page, pdf_rect, quick_mode)
            image_elements = self._extract_image_elements_optimized(page, pdf_rect, quick_mode)
            
            if not quick_mode:
                self.logger.info(f"抽出されたテキスト要素: {len(text_elements)}個")
                self.logger.info(f"抽出された画像要素: {len(image_elements)}個")

            # 分析結果を統合
            results = []

            # テキスト要素を処理
            text_results = self._process_text_elements(text_elements)
            results.extend(text_results)

            # テキスト要素が存在する場合はOCRをスキップ
            # （テキスト型PDFの場合、OCRは不要で精度も低いため）
            if len(text_results) > 0:
                if not quick_mode:
                    self.logger.info(f"✅ テキスト要素が{len(text_results)}個検出されたため、OCR処理をスキップします")
            else:
                # テキスト要素がない場合のみOCRを実行
                if not quick_mode:
                    self.logger.info("📷 テキスト要素が検出されなかったため、OCR処理を実行します")
                results.extend(self._process_image_elements_optimized(image_elements, page, ocr_language, quick_mode))

            # 読み順でソート
            results = self._sort_by_reading_order(results)
            
            # 結果が空の場合でも、診断情報を含む結果を返す
            if not results:
                if not quick_mode:
                    self.logger.info("分析結果が空のため、診断結果を作成")
                    diagnostic_info = self._create_diagnostic_info(page, pdf_rect, preview_size, selection.rect)
                else:
                    diagnostic_info = "選択範囲内にテキストが見つかりませんでした。"
                    
                default_result = AnalysisResult(
                    text=diagnostic_info,
                    element_type="diagnostic",
                    confidence=0.0,
                    bbox=(pdf_rect.x0, pdf_rect.y0, pdf_rect.x1, pdf_rect.y1),
                    reading_order=0
                )
                results = [default_result]
            
            if not quick_mode:
                self.logger.info("=" * 60)
            doc.close()
            return results
            
        except Exception as e:
            self.logger.error(f"選択範囲分析エラー: {str(e)}", exc_info=True)
            # エラーの場合でも空でない結果を返す
            error_result = AnalysisResult(
                text=f"分析エラー: {str(e)}",
                element_type="error",
                confidence=0.0,
                bbox=(0, 0, 0, 0),
                reading_order=0
            )
            return [error_result]
    
    def _convert_qt_to_pdf_coords_with_zoom(self, qt_rect: QRect, page: fitz.Page, zoom_scale: float, preview_size: tuple, quick_mode: bool = False) -> fitz.Rect:
        """Qt座標をPDF座標に変換（ズーム考慮）

        Args:
            qt_rect (QRect): Qt座標系の矩形
            page (fitz.Page): PDFページオブジェクト
            zoom_scale (float): ズーム倍率
            preview_size (tuple): プレビューウィンドウのサイズ (width, height)
            quick_mode (bool): 高速モード（ログを簡略化）

        Returns:
            fitz.Rect: PDF座標系に変換された矩形

        Note:
            アスペクト比を考慮した座標変換を行い、
            ページ範囲外の座標は自動的にクリップされる
        """
        # ページのサイズを取得
        page_rect = page.rect
        
        # ズームを考慮してQt座標を元のスケールに戻す
        actual_qt_rect = QRect(
            int(qt_rect.x() / zoom_scale),
            int(qt_rect.y() / zoom_scale),
            int(qt_rect.width() / zoom_scale),
            int(qt_rect.height() / zoom_scale)
        )
        
        # プレビューサイズもズームを考慮して調整
        preview_width, preview_height = preview_size
        actual_preview_width = int(preview_width / zoom_scale)
        actual_preview_height = int(preview_height / zoom_scale)
        
        # 実際の表示時のスケール計算（アスペクト比を考慮）
        page_aspect = page_rect.width / page_rect.height
        preview_aspect = actual_preview_width / actual_preview_height
        
        if page_aspect > preview_aspect:
            # ページが横長：幅に合わせてスケール
            scale = page_rect.width / actual_preview_width
            actual_display_height = page_rect.height / scale
            y_offset = (actual_preview_height - actual_display_height) / 2
            x_offset = 0
        else:
            # ページが縦長：高さに合わせてスケール
            scale = page_rect.height / actual_preview_height
            actual_display_width = page_rect.width / scale
            x_offset = (actual_preview_width - actual_display_width) / 2
            y_offset = 0
        
        # Qt座標をPDF座標に変換（オフセットを考慮）
        pdf_x0 = (actual_qt_rect.x() - x_offset) * scale
        pdf_y0 = (actual_qt_rect.y() - y_offset) * scale
        pdf_x1 = (actual_qt_rect.x() + actual_qt_rect.width() - x_offset) * scale
        pdf_y1 = (actual_qt_rect.y() + actual_qt_rect.height() - y_offset) * scale
        
        # 座標値の検証と補正
        if pdf_x0 < 0 or pdf_y0 < 0 or pdf_x1 > page_rect.width or pdf_y1 > page_rect.height:
            if not quick_mode:
                self.logger.warning(f"座標がページ範囲を超えています: PDF({pdf_x0:.2f}, {pdf_y0:.2f}, {pdf_x1:.2f}, {pdf_y1:.2f}) vs Page({page_rect.width:.2f}, {page_rect.height:.2f})")
            # ページ範囲内にクリップ
            pdf_x0 = max(0, pdf_x0)
            pdf_y0 = max(0, pdf_y0)
            pdf_x1 = min(page_rect.width, pdf_x1)
            pdf_y1 = min(page_rect.height, pdf_y1)
        
        # 範囲の有効性をチェック
        if pdf_x1 <= pdf_x0 or pdf_y1 <= pdf_y0:
            if not quick_mode:
                self.logger.error(f"無効な座標範囲: PDF({pdf_x0:.2f}, {pdf_y0:.2f}, {pdf_x1:.2f}, {pdf_y1:.2f})")
            # デフォルトの小さな範囲を返す
            return fitz.Rect(10, 10, 50, 50)
        
        # デバッグ情報をログ出力（通常モードのみ）
        if not quick_mode:
            self.logger.info(f"座標変換詳細 (ズーム考慮):")
            self.logger.info(f"  ズーム倍率: {zoom_scale:.3f}")
            self.logger.info(f"  元Qt座標: ({qt_rect.x()}, {qt_rect.y()}, {qt_rect.width()}, {qt_rect.height()})")
            self.logger.info(f"  調整後Qt座標: ({actual_qt_rect.x()}, {actual_qt_rect.y()}, {actual_qt_rect.width()}, {actual_qt_rect.height()})")
            self.logger.info(f"  プレビューサイズ: {preview_size} -> ({actual_preview_width}, {actual_preview_height})")
            self.logger.info(f"  ページアスペクト比: {page_aspect:.3f}")
            self.logger.info(f"  プレビューアスペクト比: {preview_aspect:.3f}")
            self.logger.info(f"  スケール: {scale:.3f}")
            self.logger.info(f"  オフセット: x={x_offset:.1f}, y={y_offset:.1f}")
            self.logger.info(f"  最終PDF座標: ({pdf_x0:.2f}, {pdf_y0:.2f}, {pdf_x1:.2f}, {pdf_y1:.2f})")
            self.logger.info(f"  ページサイズ: ({page_rect.width:.2f}, {page_rect.height:.2f})")
        
        final_rect = fitz.Rect(pdf_x0, pdf_y0, pdf_x1, pdf_y1)
        
        if not quick_mode:
            self.logger.info(f"  検証後の最終範囲: {final_rect}")
        
        return final_rect
    
    def _convert_qt_to_pdf_coords(self, qt_rect: QRect, page: fitz.Page, preview_size: tuple = None, quick_mode: bool = False) -> fitz.Rect:
        """Qt座標をPDF座標に変換（旧メソッド互換用）"""
        # ズーム倍率を1.0として新メソッドを呼び出し
        if preview_size is None:
            preview_size = (800, 600)
        return self._convert_qt_to_pdf_coords_with_zoom(qt_rect, page, 1.0, preview_size, quick_mode)
    
    def _extract_text_elements(self, page: fitz.Page, rect: fitz.Rect, quick_mode: bool = False) -> List[Dict]:
        """選択範囲内のテキスト要素を抽出"""
        try:
            # テキストブロックを取得（選択範囲でクリップ）
            text_dict = page.get_text("dict", clip=rect)
            text_elements = []
            
            for block in text_dict["blocks"]:
                if "lines" in block:  # テキストブロック
                    for line in block["lines"]:
                        for span in line["spans"]:
                            bbox = span["bbox"]
                            text = span["text"].strip()
                            if text:
                                text_elements.append({
                                    "text": text,
                                    "bbox": bbox,
                                    "font": span.get("font", ""),
                                    "size": span.get("size", 0)
                                })
                                self.logger.info(f"テキスト要素発見: '{text}' at {bbox}")
            
            return text_elements
            
        except Exception as e:
            self.logger.error(f"テキスト要素抽出エラー: {str(e)}")
            return []
    
    def _extract_image_elements_optimized(self, page: fitz.Page, rect: fitz.Rect, quick_mode: bool = False) -> List[Dict]:
        """選択範囲内の画像要素を最適化して抽出（高速版）"""
        try:
            image_elements = []
            
            if not quick_mode:
                self.logger.info(f"--- 選択範囲画像抽出（最適化版） ---")
                self.logger.info(f"選択範囲: {rect}")
            
            # 方法1: 選択範囲を低解像度で直接レンダリング（高速化）
            try:
                # 高速モードでは1.5倍、通常モードでは2倍解像度
                matrix_scale = 1.5 if quick_mode else 2.0
                pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(matrix_scale, matrix_scale))
                img_data = pix.tobytes("png")
                
                if len(img_data) > 500:  # 最小サイズチェック（通常より緩和）
                    image_elements.append({
                        "image_data": img_data,
                        "bbox": tuple(rect),
                        "xref": None,
                        "ext": "png",
                        "index": 0,
                        "method": "direct_rendering_optimized",
                        "crop_info": {
                            "original_rect": rect,
                            "cropped": True,
                            "quick_mode": quick_mode
                        }
                    })
                    if not quick_mode:
                        self.logger.info(f"最適化レンダリング成功: {len(img_data)} bytes")
                else:
                    if not quick_mode:
                        self.logger.info("最適化レンダリング: データサイズが小さすぎる")
                    
            except Exception as render_error:
                if not quick_mode:
                    self.logger.warning(f"最適化レンダリング失敗: {str(render_error)}")
            
            # 高速モードでは既存画像の詳細分析をスキップ
            if not quick_mode:
                # 通常モードのみ: 既存の画像要素から選択範囲と重複するものを抽出
                try:
                    image_list = page.get_images()
                    if len(image_list) > 0:
                        self.logger.info(f"ページ内の画像数: {len(image_list)}")
                        
                        for img_index, img in enumerate(image_list[:3]):  # 最大3つまでに制限
                            try:
                                xref = img[0]
                                img_rect = page.get_image_bbox(xref)
                                
                                # 重複チェック（簡略化）
                                if rect.intersects(img_rect):
                                    try:
                                        base_image = page.parent.extract_image(xref)
                                        img_data = base_image["image"]
                                        
                                        if len(img_data) > 1000:
                                            image_elements.append({
                                                "image_data": img_data,
                                                "bbox": tuple(img_rect),
                                                "xref": xref,
                                                "ext": base_image["ext"],
                                                "index": img_index + 1,
                                                "method": "existing_image_intersection"
                                            })
                                            
                                    except Exception as extract_error:
                                        self.logger.warning(f"既存画像抽出失敗 {img_index + 1}: {str(extract_error)}")
                                        
                            except Exception as img_error:
                                continue
                                
                except Exception as list_error:
                    self.logger.warning(f"画像リスト処理エラー: {str(list_error)}")
            
            if not quick_mode:
                self.logger.info(f"最適化抽出完了: {len(image_elements)}個の画像要素")
            
            return image_elements
            
        except Exception as e:
            self.logger.error(f"最適化画像抽出エラー: {str(e)}")
            return []
    
    def _extract_image_elements_with_cropping(self, page: fitz.Page, rect: fitz.Rect) -> List[Dict]:
        """選択範囲内の画像要素を抽出し、選択範囲で切り抜き"""
        try:
            image_elements = []
            
            self.logger.info(f"--- 選択範囲画像抽出（切り抜きあり） ---")
            self.logger.info(f"選択範囲: {rect}")
            
            # 方法1: 選択範囲を画像として直接レンダリング（最も確実）
            try:
                # 選択範囲の画像を直接取得
                pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2.0, 2.0))  # 2倍解像度
                img_data = pix.tobytes("png")
                
                if len(img_data) > 1000:  # 最小サイズチェック
                    image_elements.append({
                        "image_data": img_data,
                        "bbox": tuple(rect),
                        "xref": None,  # 直接レンダリングなのでxrefはなし
                        "ext": "png",
                        "index": 0,
                        "method": "direct_rendering",
                        "crop_info": {
                            "original_rect": rect,
                            "cropped": True
                        }
                    })
                    self.logger.info(f"直接レンダリング成功: {len(img_data)} bytes")
                else:
                    self.logger.info("直接レンダリング: データサイズが小さすぎる")
                    
            except Exception as render_error:
                self.logger.warning(f"直接レンダリング失敗: {str(render_error)}")
            
            # 方法2: 既存の画像要素から選択範囲と重複するものを抽出して切り抜き
            try:
                image_list = page.get_images()
                self.logger.info(f"ページ内の画像数: {len(image_list)}")
                
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        
                        # 画像の位置を取得
                        try:
                            img_rect = page.get_image_bbox(xref)
                            self.logger.info(f"画像 {img_index + 1}: 位置 {img_rect}")
                        except Exception as bbox_error:
                            self.logger.warning(f"画像 {img_index + 1}: 位置取得失敗 - {str(bbox_error)}")
                            continue  # 位置が取得できない画像はスキップ
                        
                        # 選択範囲との重複をチェック
                        if rect.intersects(img_rect):
                            intersection = rect & img_rect
                            if intersection.width > 5 and intersection.height > 5:  # 最小重複サイズ
                                self.logger.info(f"画像 {img_index + 1}: 選択範囲と重複 {intersection}")
                                
                                # 画像データを取得
                                try:
                                    base_image = page.parent.extract_image(xref)
                                    original_image_data = base_image["image"]
                                    
                                    # PIL Imageで開いて切り抜き
                                    pil_image = Image.open(io.BytesIO(original_image_data))
                                    
                                    # 画像座標での切り抜き範囲を計算
                                    # 注意: PDF座標と画像座標は異なる可能性がある
                                    img_width, img_height = pil_image.size
                                    
                                    # PDF座標を画像座標に変換
                                    # 画像の実際の範囲 (img_rect) を画像サイズ (img_width, img_height) にマッピング
                                    scale_x = img_width / img_rect.width if img_rect.width > 0 else 1
                                    scale_y = img_height / img_rect.height if img_rect.height > 0 else 1
                                    
                                    # 選択範囲を画像座標に変換
                                    crop_x0 = max(0, int((rect.x0 - img_rect.x0) * scale_x))
                                    crop_y0 = max(0, int((rect.y0 - img_rect.y0) * scale_y))
                                    crop_x1 = min(img_width, int((rect.x1 - img_rect.x0) * scale_x))
                                    crop_y1 = min(img_height, int((rect.y1 - img_rect.y0) * scale_y))
                                    
                                    self.logger.info(f"切り抜き座標: ({crop_x0}, {crop_y0}, {crop_x1}, {crop_y1})")
                                    
                                    # 有効な切り抜き範囲かチェック
                                    if crop_x1 > crop_x0 and crop_y1 > crop_y0:
                                        # 画像を切り抜き
                                        cropped_image = pil_image.crop((crop_x0, crop_y0, crop_x1, crop_y1))
                                        
                                        # PNG形式で保存
                                        img_buffer = io.BytesIO()
                                        cropped_image.save(img_buffer, format='PNG')
                                        cropped_data = img_buffer.getvalue()
                                        
                                        image_elements.append({
                                            "image_data": cropped_data,
                                            "bbox": tuple(intersection),  # 重複領域をbboxとして使用
                                            "xref": xref,
                                            "ext": "png",
                                            "index": img_index,
                                            "method": "cropped_from_existing",
                                            "crop_info": {
                                                "original_rect": img_rect,
                                                "crop_rect": (crop_x0, crop_y0, crop_x1, crop_y1),
                                                "cropped": True,
                                                "original_size": pil_image.size,
                                                "cropped_size": cropped_image.size
                                            }
                                        })
                                        
                                        self.logger.info(f"画像 {img_index + 1} を切り抜き: {cropped_image.size}")
                                    else:
                                        self.logger.warning(f"画像 {img_index + 1}: 無効な切り抜き範囲")
                                        
                                except Exception as crop_error:
                                    self.logger.error(f"画像 {img_index + 1} 切り抜きエラー: {str(crop_error)}")
                            else:
                                self.logger.info(f"画像 {img_index + 1}: 重複が小さすぎるためスキップ")
                        else:
                            self.logger.info(f"画像 {img_index + 1}: 選択範囲と重複なし")
                            
                    except Exception as img_error:
                        self.logger.error(f"画像 {img_index + 1} 処理エラー: {str(img_error)}")
                        continue
                        
            except Exception as extract_error:
                self.logger.error(f"既存画像抽出エラー: {str(extract_error)}")
            
            self.logger.info(f"最終的に抽出された画像要素: {len(image_elements)}個")
            return image_elements
            
        except Exception as e:
            self.logger.error(f"画像要素抽出エラー: {str(e)}")
            return []
    
    def _create_diagnostic_info(self, page: fitz.Page, pdf_rect: fitz.Rect, preview_size: tuple, qt_rect: QRect) -> str:
        """診断情報を作成"""
        info_parts = []
        info_parts.append("【診断情報】")
        info_parts.append(f"Qt選択: {qt_rect.x()},{qt_rect.y()},{qt_rect.width()},{qt_rect.height()}")
        info_parts.append(f"PDF座標: {pdf_rect}")
        info_parts.append(f"プレビューサイズ: {preview_size}")
        
        # 画像情報（エラー対応）
        try:
            image_list = page.get_images()
            info_parts.append(f"ページ内画像数: {len(image_list)}")
            
            # 直接レンダリングのテスト
            try:
                pix = page.get_pixmap(clip=pdf_rect)
                info_parts.append(f"直接レンダリングサイズ: {pix.width}x{pix.height}")
            except Exception as render_error:
                info_parts.append(f"直接レンダリングエラー: {str(render_error)[:50]}...")
            
            for i, img in enumerate(image_list[:3]):  # 最初の3つまで
                try:
                    xref = img[0]
                    try:
                        img_rect = page.get_image_bbox(xref)
                        intersects = pdf_rect.intersects(img_rect)
                        info_parts.append(f"画像{i+1}: {img_rect} (重複:{intersects})")
                    except Exception as bbox_error:
                        info_parts.append(f"画像{i+1}: 位置取得エラー ({str(bbox_error)[:30]}...)")
                        
                except Exception as img_error:
                    info_parts.append(f"画像{i+1}: 処理エラー ({str(img_error)[:30]}...)")
                
        except Exception as e:
            info_parts.append(f"画像情報取得エラー: {str(e)}")
        
        # テキスト情報
        try:
            text = page.get_text(clip=pdf_rect)
            info_parts.append(f"テキスト長: {len(text)}")
            if text.strip():
                info_parts.append(f"テキストサンプル: {text[:50]}...")
        except Exception as e:
            info_parts.append(f"テキスト情報取得エラー: {str(e)}")
        
        return "\n".join(info_parts)
    
    def _process_text_elements(self, text_elements: List[Dict]) -> List[AnalysisResult]:
        """テキスト要素を処理"""
        results = []
        
        for element in text_elements:
            result = AnalysisResult(
                text=element["text"],
                element_type="text",
                confidence=1.0,  # テキストは確実
                bbox=element["bbox"],
                reading_order=0  # 後でソート時に設定
            )
            results.append(result)
        
        return results
    
    def _process_image_elements_optimized(self, image_elements: List[Dict], page: fitz.Page, ocr_language: str = 'jpn+eng', quick_mode: bool = False) -> List[AnalysisResult]:
        """画像要素をOCR処理（最適化版）"""
        results = []
        
        # 大量の画像要素がある場合はメモリ使用量をチェック
        if len(image_elements) > 5 and not self._check_memory_usage():
            self.logger.warning("メモリ不足のため、OCR処理を制限します")
            image_elements = image_elements[:3]  # 最初の3つの要素のみ処理
        
        if not quick_mode:
            self.logger.info(f"OCR処理開始（最適化版）: {len(image_elements)}個の画像要素")
        
        for idx, element in enumerate(image_elements):
            try:
                if not quick_mode:
                    self.logger.info(f"画像要素 {element.get('index', idx)} のOCR処理を開始")
                
                # 画像をPIL Imageに変換（メモリエラー対応）
                try:
                    image_bytes = element["image_data"]
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    
                    # 画像が大きすぎる場合はリサイズ
                    if pil_image.size[0] * pil_image.size[1] > 4000000:  # 4M pixels以上
                        self.logger.warning(f"画像が大きすぎるためリサイズします: {pil_image.size}")
                        max_dimension = 2000
                        ratio = min(max_dimension / pil_image.size[0], max_dimension / pil_image.size[1])
                        new_size = (int(pil_image.size[0] * ratio), int(pil_image.size[1] * ratio))
                        pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)
                    
                    if not quick_mode:
                        self.logger.info(f"画像サイズ: {pil_image.size}, モード: {pil_image.mode}")
                        
                except MemoryError as me:
                    # メモリ不足エラー
                    self.error_handler.handle_error(me, ErrorType.MEMORY_ERROR, show_dialog=False)
                    self.logger.error(f"画像変換でメモリ不足 (要素 {idx})")
                    continue
                except Exception as ie:
                    self.logger.error(f"画像変換エラー (要素 {idx}): {str(ie)}")
                    continue

                # OCR設定（日本語優先設定）
                if quick_mode:
                    # 高速モード：日本語と英語を併用、文字制限を最小限に
                    ocr_config = '--oem 3 --psm 6 -c preserve_interword_spaces=1'
                else:
                    # 通常モード：日本語優先で詳細設定
                    ocr_config = (
                        '--oem 3 --psm 6 '
                        '-c preserve_interword_spaces=1 '
                        '-c tessedit_char_blacklist=§°¢£¤¥¦©«®±²³´µ¶·¸¹º»¼½¾'
                    )
                
                # OCR実行（選択された言語で）
                # まず元画像で実行する。Tesseract 5は内部前処理が優秀で、
                # 品質の良い画像に補正を常時かけると逆に精度が落ちるため
                if ocr_language == 'auto':
                    # 自動検出モード
                    text = self._auto_detect_language_ocr(pil_image, ocr_config, quick_mode)
                else:
                    # 指定された言語でOCR実行
                    text = pytesseract.image_to_string(pil_image, config=ocr_config, lang=ocr_language)

                    # 日本語が含まれている場合のフォールバック
                    if ocr_language == 'jpn+eng' and (not text.strip() or not self._contains_japanese_text(text)):
                        text_jpn = pytesseract.image_to_string(pil_image, config='--oem 3 --psm 6', lang='jpn')
                        if text_jpn.strip() and self._contains_japanese_text(text_jpn):
                            text = text_jpn
                            if not quick_mode:
                                self.logger.info(f"日本語専用OCRで再試行: '{text[:50]}{'...' if len(text) > 50 else ''}'")

                # フォールバック: 元画像で意味のある結果が得られなかった場合のみ、
                # 補正画像（ノイズ除去・拡大）で再試行する。スキャン品質が低い
                # レシート対策。元画像で読めた場合の結果には一切影響しない
                if not self._ocr_text_looks_valid(text):
                    for variant_idx, variant in enumerate(preprocess_variants(pil_image, self.logger)):
                        retry_text = pytesseract.image_to_string(variant, config=ocr_config, lang='jpn+eng' if ocr_language == 'auto' else ocr_language)
                        if self._ocr_text_looks_valid(retry_text):
                            text = retry_text
                            if not quick_mode:
                                self.logger.info(f"補正画像(変種{variant_idx + 1})でのOCR再試行に成功: '{text.strip()[:30]}...'")
                            break
                
                if text and text.strip():
                    confidence = 0.8 if quick_mode else 0.9  # 高速モードでは信頼度を少し下げる
                    result = AnalysisResult(
                        text=text.strip(),
                        element_type="image",
                        confidence=confidence,
                        bbox=element["bbox"],
                        reading_order=idx
                    )
                    results.append(result)
                    
                    if not quick_mode:
                        self.logger.info(f"OCR成功: '{text.strip()[:30]}...'")
                else:
                    if not quick_mode:
                        self.logger.info("OCR結果が空またはテキストなし")
                
            except Exception as e:
                # OCRエラーを分類してフォールバック処理
                error_type = self.error_handler.classify_ocr_error(e)
                
                if not quick_mode:
                    self.logger.error(f"OCR処理エラー (要素 {idx}): {str(e)}")
                
                # フォールバック処理を試行
                fallback_result = self._try_ocr_fallback(pil_image, element, idx, quick_mode)
                if fallback_result:
                    results.append(fallback_result)
                
                continue
        
        if not quick_mode:
            self.logger.info(f"OCR処理完了: {len(results)}個の結果")
        
        return results
    
    def _process_image_elements(self, image_elements: List[Dict], page: fitz.Page) -> List[AnalysisResult]:
        """画像要素をOCR処理"""
        results = []
        
        self.logger.info(f"OCR処理開始: {len(image_elements)}個の画像要素")
        
        for idx, element in enumerate(image_elements):
            try:
                self.logger.info(f"画像要素 {element.get('index', idx)} のOCR処理を開始")
                
                # 画像をPIL Imageに変換
                image_bytes = element["image_data"]
                pil_image = Image.open(io.BytesIO(image_bytes))
                
                self.logger.info(f"画像サイズ: {pil_image.size}, モード: {pil_image.mode}")
                
                # 切り抜き情報をログ出力
                crop_info = element.get("crop_info", {})
                method = element.get("method", "unknown")
                self.logger.info(f"処理方法: {method}")
                if crop_info:
                    self.logger.info(f"切り抜き情報: {crop_info}")
                
                # 画像が小さすぎる場合でも結果を作成
                if pil_image.width < 10 or pil_image.height < 10:
                    self.logger.info("画像が小さすぎますが、結果を作成します")
                    result = AnalysisResult(
                        text=f"画像が小さすぎます (サイズ: {pil_image.size}, 方法: {method})",
                        element_type="image",
                        confidence=0.0,
                        bbox=element["bbox"],
                        reading_order=0
                    )
                    results.append(result)
                    continue
                
                # OCR処理を試行
                ocr_success = False
                extracted_text = ""
                confidence = 0.0
                
                try:
                    # Tesseractが利用可能かチェック
                    self.logger.info("Tesseractでのテキスト抽出を開始")
                    
                    # 画像前処理を試行
                    processed_images = self._preprocess_image_for_ocr(pil_image)
                    
                    # 最適化されたOCR設定（処理時間短縮 + 品質向上）
                    # OCR言語設定に応じて設定を変更
                    ocr_configs = self._get_ocr_configs_for_language(ocr_language)
                    
                    best_text = ""
                    best_confidence = 0
                    
                    for config_idx, ocr_config in enumerate(ocr_configs):
                        try:
                            # 各画像前処理版でOCRを試行
                            for img_variant_name, img_variant in processed_images.items():
                                try:
                                    test_text = pytesseract.image_to_string(
                                        img_variant,
                                        lang=ocr_config['lang'],
                                        config=ocr_config['config']
                                    ).strip()
                                    
                                    # 無効な文字をフィルタリング
                                    test_text = self._filter_invalid_characters(test_text)
                                    
                                    if test_text:
                                        self.logger.info(f"OCR設定{config_idx+1}({img_variant_name}): '{test_text[:30]}{'...' if len(test_text) > 30 else ''}'")
                                        
                                        # 改良された品質評価
                                        text_score = self._evaluate_ocr_quality(test_text, ocr_config)
                                        
                                        if text_score > best_confidence:
                                            best_confidence = text_score
                                            best_text = test_text
                                            self.logger.info(f"新しい最良結果: スコア{text_score:.1f}, テキスト: '{test_text[:20]}...'")
                                            
                                            # 十分に良い結果が得られた場合は早期終了
                                            if text_score > 50:
                                                self.logger.info("十分な品質の結果が得られたため、OCR処理を終了")
                                                break
                                        
                                except Exception as variant_error:
                                    self.logger.debug(f"OCR設定{config_idx+1}({img_variant_name})でエラー: {str(variant_error)}")
                                    continue
                            
                            # 早期終了条件をチェック
                            if best_confidence > 50:
                                break
                                        
                        except Exception as config_error:
                            self.logger.debug(f"OCR設定 {ocr_config} でエラー: {str(config_error)}")
                            continue
                    
                    extracted_text = best_text
                    
                    self.logger.info(f"OCR結果 (長さ {len(extracted_text)}): '{extracted_text[:50]}{'...' if len(extracted_text) > 50 else ''}'")
                    
                    if extracted_text:
                        ocr_success = True
                        confidence = min(best_confidence / 20.0, 1.0)  # スコアを0-1に正規化
                    else:
                        self.logger.info("OCRでテキストが抽出されませんでした")
                
                except Exception as ocr_error:
                    self.logger.error(f"OCR処理エラー: {str(ocr_error)}")
                
                # 結果を作成（OCRが失敗しても画像要素として記録）
                if ocr_success and extracted_text:
                    result_text = extracted_text
                    result_confidence = confidence
                else:
                    result_text = f"画像要素 (OCR失敗またはテキストなし) - サイズ: {pil_image.size}, 方法: {method}"
                    if crop_info.get("cropped"):
                        result_text += f", 切り抜きサイズ: {crop_info.get('cropped_size', 'unknown')}"
                    result_confidence = 0.0
                
                result = AnalysisResult(
                    text=result_text,
                    element_type="image",
                    confidence=result_confidence,
                    bbox=element["bbox"],
                    reading_order=0
                )
                results.append(result)
                
                self.logger.info(f"画像要素 {element.get('index', idx)} の処理完了: '{result_text[:30]}{'...' if len(result_text) > 30 else ''}'")
                
            except Exception as e:
                self.logger.error(f"画像要素処理エラー: {str(e)}", exc_info=True)
                # エラーでも結果を作成
                error_result = AnalysisResult(
                    text=f"画像処理エラー: {str(e)[:50]}",
                    element_type="image",
                    confidence=0.0,
                    bbox=element.get("bbox", (0, 0, 0, 0)),
                    reading_order=0
                )
                results.append(error_result)
        
        self.logger.info(f"OCR処理完了: {len(results)}個の結果")
        return results
    
    def _preprocess_image_for_ocr(self, pil_image: Image.Image) -> Dict[str, Image.Image]:
        """OCR用の画像前処理"""
        processed_images = {}
        
        try:
            # オリジナル画像
            processed_images["original"] = pil_image
            
            # グレースケール変換
            if pil_image.mode != 'L':
                gray_image = pil_image.convert('L')
                processed_images["grayscale"] = gray_image
            
            # コントラスト強化
            try:
                from PIL import ImageEnhance
                if pil_image.mode != 'L':
                    enhancer = ImageEnhance.Contrast(pil_image.convert('L'))
                else:
                    enhancer = ImageEnhance.Contrast(pil_image)
                contrast_image = enhancer.enhance(2.0)  # コントラストを2倍に
                processed_images["contrast"] = contrast_image
            except ImportError:
                self.logger.debug("PIL.ImageEnhance not available, skipping contrast enhancement")
            
            # リサイズ（小さすぎる画像を拡大）
            if pil_image.width < 100 or pil_image.height < 100:
                scale_factor = max(2, 100 / min(pil_image.width, pil_image.height))
                new_size = (int(pil_image.width * scale_factor), int(pil_image.height * scale_factor))
                resized_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)
                processed_images["resized"] = resized_image
            
        except Exception as e:
            self.logger.error(f"画像前処理エラー: {str(e)}")
            # エラーの場合はオリジナルのみ返す
            processed_images = {"original": pil_image}
        
        return processed_images
    
    def _filter_invalid_characters(self, text: str) -> str:
        """無効な文字をフィルタリング"""
        if not text:
            return text
        
        # 明らかに無効な文字パターンを除去
        invalid_chars = set('§°¢£¤¥¦©«®±²³´µ¶·¸¹º»¼½¾¿')
        
        # 文字を1つずつチェック
        filtered_chars = []
        for char in text:
            if char not in invalid_chars:
                filtered_chars.append(char)
        
        result = ''.join(filtered_chars)
        
        # 連続する特殊文字や意味不明なパターンを除去
        import re
        
        # 連続する|や記号を除去
        result = re.sub(r'[|§°]{2,}', '', result)
        
        # 単独の記号行を除去
        lines = result.split('\n')
        valid_lines = []
        for line in lines:
            line = line.strip()
            # 日本語文字または英数字が含まれる行のみ保持
            if line and (self._contains_japanese_text(line) or re.search(r'[a-zA-Z0-9]', line)):
                valid_lines.append(line)
        
        return '\n'.join(valid_lines).strip()
    
    def _ocr_text_looks_valid(self, text: str) -> bool:
        """OCR結果に意味のある内容（日本語または英数字）が含まれているか

        補正画像でのOCR再試行を行うかどうかの判定に使う。
        空文字や記号のみの結果は「失敗」とみなす。
        """
        if not text or not text.strip():
            return False
        if self._contains_japanese_text(text):
            return True
        return any(ch.isascii() and ch.isalnum() for ch in text)

    def _contains_japanese_text(self, text: str) -> bool:
        """テキストに日本語文字が含まれているかチェック"""
        if not text:
            return False
        
        # ひらがな、カタカナ、漢字の範囲をチェック
        japanese_ranges = [
            (0x3040, 0x309F),  # ひらがな
            (0x30A0, 0x30FF),  # カタカナ
            (0x4E00, 0x9FAF),  # CJK統合漢字
            (0x3400, 0x4DBF),  # CJK拡張A
            (0xFF66, 0xFF9D),  # 半角カタカナ
        ]
        
        for char in text:
            char_code = ord(char)
            for start, end in japanese_ranges:
                if start <= char_code <= end:
                    return True
        return False
    
    def _auto_detect_language_ocr(self, pil_image, ocr_config: str, quick_mode: bool) -> str:
        """言語を自動検出してOCRを実行"""
        # 日本語優先で試行
        text_jpn = pytesseract.image_to_string(pil_image, config=ocr_config, lang='jpn+eng')
        
        if text_jpn.strip() and self._contains_japanese_text(text_jpn):
            if not quick_mode:
                self.logger.info(f"日本語検出: '{text_jpn[:50]}{'...' if len(text_jpn) > 50 else ''}'")
            return text_jpn
        
        # 日本語が検出されない場合は英語で試行
        text_eng = pytesseract.image_to_string(pil_image, config=ocr_config, lang='eng')
        
        if not quick_mode:
            self.logger.info(f"英語でフォールバック: '{text_eng[:50]}{'...' if len(text_eng) > 50 else ''}'")
        
        return text_eng if text_eng.strip() else text_jpn
    
    def _get_ocr_configs_for_language(self, ocr_language: str) -> list:
        """言語に応じたOCR設定を取得"""
        if ocr_language == 'jpn+eng':
            return [
                # 日本語優先設定
                {'lang': 'jpn+eng', 'config': '--psm 6 -c preserve_interword_spaces=1'},
                {'lang': 'jpn', 'config': '--psm 6 -c preserve_interword_spaces=1'},
                {'lang': 'jpn+eng', 'config': '--psm 3'},
                {'lang': 'jpn+eng', 'config': '--psm 7'},
            ]
        elif ocr_language == 'jpn':
            return [
                # 日本語のみ
                {'lang': 'jpn', 'config': '--psm 6 -c preserve_interword_spaces=1'},
                {'lang': 'jpn', 'config': '--psm 3'},
                {'lang': 'jpn', 'config': '--psm 7'},
            ]
        elif ocr_language == 'eng':
            return [
                # 英語のみ
                {'lang': 'eng', 'config': '--psm 6 -c preserve_interword_spaces=1'},
                {'lang': 'eng', 'config': '--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,:-¥$€()[]'},
                {'lang': 'eng', 'config': '--psm 8 -c tessedit_char_whitelist=0123456789.,¥$€'},
            ]
        else:
            # デフォルト（日本語優先）
            return self._get_ocr_configs_for_language('jpn+eng')
    
    def _evaluate_ocr_quality(self, text: str, ocr_config: dict) -> float:
        """OCR結果の品質を評価"""
        if not text or not text.strip():
            return 0.0
        
        score = 0.0
        
        # 基本スコア（文字数）
        text_length = len(text.replace(' ', '').replace('\n', ''))
        score += min(text_length, 20)  # 最大20点
        
        # 日本語文字の検出
        japanese_chars = sum(1 for char in text if '\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF' or '\u4E00' <= char <= '\u9FAF')
        if japanese_chars > 0 and 'jpn' in ocr_config['lang']:
            score += japanese_chars * 2  # 日本語文字1つにつき2点
        
        # 数字の検出
        digit_chars = sum(1 for char in text if char.isdigit())
        if digit_chars > 0:
            score += digit_chars * 1.5  # 数字1つにつき1.5点
        
        # 英字の検出
        alpha_chars = sum(1 for char in text if char.isalpha() and ord(char) < 128)
        if alpha_chars > 0:
            score += alpha_chars * 1  # 英字1つにつき1点
        
        # 意味のある単語パターンの検出
        import re
        
        # 金額パターン
        if re.search(r'\d+[,.]?\d*\s*[円¥$€]', text):
            score += 15
        
        # 日付パターン
        if re.search(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}', text):
            score += 10
        
        # 請求書関連単語
        invoice_words = ['請求書', '領収書', 'invoice', 'receipt', '合計', 'total', '税込', '税抜']
        for word in invoice_words:
            if word.lower() in text.lower():
                score += 8
        
        # 無効文字のペナルティ
        invalid_char_count = sum(1 for char in text if char in '§|°¢£¤¥¦©«®±²³´µ¶·¸¹º»¼½¾¿')
        score -= invalid_char_count * 0.5
        
        # 文字の多様性ボーナス
        unique_chars = len(set(text.replace(' ', '').replace('\n', '')))
        if unique_chars > 5:
            score += min(unique_chars - 5, 10)  # 最大10点のボーナス
        
        return max(score, 0.0)
    
    def _sort_by_reading_order(self, results: List[AnalysisResult]) -> List[AnalysisResult]:
        """座標情報に基づいて読み順でソート（Y座標許容誤差対応）

        Y座標が近い要素（同じ行）を正しくソートするため、設定ファイルから
        許容誤差を読み込んで適用します。

        設定: config.toml の [ocr] セクション
        - y_coordinate_tolerance: Y座標の許容誤差（ポイント単位、デフォルト: 2.0）

        Example:
            和暦「令和7年9月16日」で数字と漢字のY座標が微妙にずれている場合:
            - Y座標許容誤差 2.0 の場合、56.09と56.43は同じ行として扱われる
            - X座標順（左から右）にソート: 令和 7 年 9 月 16 日

        Returns:
            List[AnalysisResult]: 読み順でソートされた結果リスト
        """
        # 設定ファイルからY座標許容誤差を取得
        y_tolerance = self.config_manager.get_y_coordinate_tolerance()

        # Y座標を許容誤差内で丸めてソート（同じ行はX座標順）
        sorted_results = sorted(
            results,
            key=lambda r: (round(r.bbox[1] / y_tolerance) * y_tolerance, r.bbox[0])
        )

        # reading_orderを設定
        for i, result in enumerate(sorted_results):
            result.reading_order = i

        return sorted_results
    
    def combine_results(self, results: List[AnalysisResult]) -> str:
        """分析結果を統合して単一のテキストとして返す"""
        if not results:
            return ""
        
        # 読み順でソート済みの結果を結合
        combined_texts = []
        for result in results:
            if result.text.strip():
                combined_texts.append(result.text.strip())
        
        return ' '.join(combined_texts)
    
    def get_detailed_analysis(self, results: List[AnalysisResult]) -> Dict:
        """詳細な分析情報を返す"""
        if not results:
            return {
                "total_elements": 0,
                "text_elements": 0,
                "image_elements": 0,
                "combined_text": "選択範囲内に要素が見つかりませんでした",
                "average_confidence": 0.0
            }
        
        text_count = sum(1 for r in results if r.element_type == "text")
        image_count = sum(1 for r in results if r.element_type == "image")
        error_count = sum(1 for r in results if r.element_type in ["error", "unknown", "diagnostic"])
        avg_confidence = sum(r.confidence for r in results) / len(results)
        
        return {
            "total_elements": len(results),
            "text_elements": text_count,
            "image_elements": image_count,
            "error_elements": error_count,
            "combined_text": self.combine_results(results),
            "average_confidence": avg_confidence,
            "details": [
                {
                    "text": r.text,
                    "type": r.element_type,
                    "confidence": r.confidence,
                    "bbox": r.bbox
                }
                for r in results
            ]
        }
    
    def _try_ocr_fallback(self, pil_image: Image.Image, element: Dict, idx: int, quick_mode: bool = False) -> Optional[AnalysisResult]:
        """OCR処理失敗時のフォールバック処理"""
        try:
            if not quick_mode:
                self.logger.info(f"OCRフォールバック処理開始 (要素 {idx})")
            
            # 1. より簡単なOCR設定で再試行
            fallback_configs = [
                '--psm 8',  # 単一の単語として扱う
                '--psm 7',  # 単一のテキストライン
                '--psm 6',  # 単一のブロック
                '--psm 3',  # 自動的にページレイアウトを判定
            ]
            
            for config in fallback_configs:
                try:
                    text = pytesseract.image_to_string(pil_image, config=config, lang='jpn+eng')
                    if text and text.strip():
                        if not quick_mode:
                            self.logger.info(f"フォールバック成功 (config: {config}): '{text.strip()[:30]}...'")
                        
                        return AnalysisResult(
                            text=text.strip(),
                            element_type="image_fallback",
                            confidence=0.3,  # フォールバックなので低めの信頼度
                            bbox=element.get('bbox', (0, 0, 0, 0)),
                            source="OCR_fallback"
                        )
                except Exception:
                    continue
            
            # 2. 画像を前処理して再試行
            try:
                processed_image = self._simple_image_preprocessing(pil_image)
                text = pytesseract.image_to_string(processed_image, config='--psm 6', lang='jpn+eng')
                if text and text.strip():
                    if not quick_mode:
                        self.logger.info(f"前処理フォールバック成功: '{text.strip()[:30]}...'")
                    
                    return AnalysisResult(
                        text=text.strip(),
                        element_type="image_preprocessed",
                        confidence=0.2,
                        bbox=element.get('bbox', (0, 0, 0, 0)),
                        source="OCR_preprocessed"
                    )
            except Exception:
                pass
            
            # 3. 画像情報のみを返す（OCR失敗）
            if not quick_mode:
                self.logger.info(f"全てのフォールバック処理が失敗、画像情報のみ返却")
            
            return AnalysisResult(
                text=f"画像要素 (OCR失敗) - サイズ: {pil_image.size}",
                element_type="image_no_text",
                confidence=0.0,
                bbox=element.get('bbox', (0, 0, 0, 0)),
                source="fallback_image_only"
            )
            
        except Exception as e:
            if not quick_mode:
                self.logger.error(f"フォールバック処理でもエラー: {str(e)}")
            return None
    
    def _simple_image_preprocessing(self, image: Image.Image) -> Image.Image:
        """OCRフォールバック用の簡単な画像前処理"""
        try:
            # グレースケール変換
            if image.mode != 'L':
                image = image.convert('L')
            
            # サイズが小さすぎる場合は拡大
            if image.size[0] < 100 or image.size[1] < 30:
                scale_factor = max(100 / image.size[0], 30 / image.size[1])
                new_size = (int(image.size[0] * scale_factor), int(image.size[1] * scale_factor))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            return image
            
        except Exception:
            return image
    
    def _check_memory_usage(self) -> bool:
        """メモリ使用量をチェック（簡易版）"""
        try:
            import psutil
            memory_percent = psutil.virtual_memory().percent
            if memory_percent > 85:  # メモリ使用率85%以上で警告
                self.logger.warning(f"メモリ使用率が高くなっています: {memory_percent:.1f}%")
                return False
            return True
        except ImportError:
            # psutilがない場合はチェックをスキップ
            return True
        except Exception:
            return True