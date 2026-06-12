"""OCR前処理ユーティリティ

スキャン品質が低いPDF（感熱紙レシートの薄い印字、ごま塩ノイズ、
低解像度の切り抜き）でOCRが失敗したときの「再試行用」画像補正。

設計方針（合成劣化画像での比較実験に基づく）:
- Tesseract 5 は内部前処理（二値化等）が優秀で、品質の良い画像に
  固定パラメータの補正を常時かけると逆に精度が落ちることを確認した。
  そのため補正は「元画像でのOCRが失敗したときのフォールバック」と
  してのみ使う。元画像で読める場合の結果は一切変わらない
- 自動適用・設定なし。ユーザーが調整するパラメータは設けない
- OCRに渡す画像にのみ適用し、画面のプレビュー表示には影響させない
- 失敗しても例外を投げず、生成できた変種のみを返す

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""

from typing import List

from PIL import Image, ImageFilter

# Tesseractは文字が小さい（目安: 文字高20px未満）と精度が急落するため、
# 短辺がこの値を下回る切り抜き画像は拡大してから補正する
_MIN_DIMENSION = 600

# 拡大倍率
_UPSCALE_FACTOR = 2

# 拡大後の上限ピクセル数（メモリ保護。呼び出し側の4Mピクセル制限と整合）
_MAX_PIXELS = 4_000_000


def _to_grayscale_upscaled(pil_image: Image.Image) -> Image.Image:
    """グレースケール化し、小さい画像は拡大して返す"""
    img = pil_image
    if img.mode != 'L':
        img = img.convert('L')
    if (min(img.size) < _MIN_DIMENSION
            and img.width * img.height * _UPSCALE_FACTOR ** 2 <= _MAX_PIXELS):
        img = img.resize(
            (img.width * _UPSCALE_FACTOR, img.height * _UPSCALE_FACTOR),
            Image.Resampling.LANCZOS,
        )
    return img


def preprocess_variants(pil_image: Image.Image, logger=None) -> List[Image.Image]:
    """OCR再試行用の補正画像バリエーションを生成する

    元画像でのOCRが空・無意味な結果だった場合に、これらの変種で
    順に再試行することを想定している。比較実験でノイズ画像からの
    復元実績があった構成のみを採用:

        1. グレースケール + 拡大 + メディアンフィルタ(3) … 軽いノイズ除去
        2. グレースケール + 拡大 + メディアンフィルタ(5) … 強いノイズ除去

    Args:
        pil_image (Image.Image): 元画像。この画像自体は変更しない
        logger (logging.Logger, optional): 失敗時のデバッグログ出力先

    Returns:
        List[Image.Image]: 補正済み画像のリスト。失敗時は空リスト
    """
    variants = []
    try:
        base = _to_grayscale_upscaled(pil_image)
        variants.append(base.filter(ImageFilter.MedianFilter(3)))
        variants.append(base.filter(ImageFilter.MedianFilter(5)))
    except Exception as e:
        if logger is not None:
            logger.debug(f"OCR用の補正画像生成に失敗しました: {e}")
    return variants
