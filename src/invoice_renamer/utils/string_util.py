"""
文字列操作に関するユーティリティ関数群を提供します。
Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""
import re
from dateutil.parser import parse


###抽出した文字列を組み合わせてファイル名を作成します。
def generate_filename(extracted_texts):
    result_file_name = ""

    # 日付
    result_file_name = result_file_name + "2024-"

    # 取引先
    partner_name = ""

    # 金額
    price = convert_date_text(12,000,000)

    # 拡張子
    ".pdf"

    # テキストから日付や金額を抽出するロジック
    # 例: 正規表現で日付や金額を特定



###テキストから数字のみを抽出
def extract_numeric(amount):
    #全角または半角の数字のみ抽出
    numeric_string = re.sub(r'[^\d０-９]', '', amount)
    #抽出結果をすべて半角数字に置換
    numeric_string = normalize_numeric(numeric_string)
    return numeric_string

###全角数字を半角数字に置換
def normalize_numeric(numeric):
    fullwidth_digits = '０１２３４５６７８９'
    halfwidth_digits = '0123456789'
    translation_table = str.maketrans(fullwidth_digits, halfwidth_digits) 
    return numeric.translate(translation_table)

# テスト
input_string = "a1b２c３d４"
result = extract_numeric(input_string)
print(f"元の文字列: {input_string}")
print(f"数字のみ（半角に変換）: {result}")



###日付文字列の解析
def parse_date(date_str):
    try:
        # 文字列型の日付値をDate型に変換
        return parse(date_str, fuzzy=True)
    except ValueError as e :
        print(f"'{date_str}'の解析に失敗しました")
        return None

###日付データを指定のフォーマットの文字列に変換
def change_date_format(date, to_format):
    try:
        # 指定フォーマットの文字列に変換
        return date.strftime(to_format)
    except (ValueError, AttributeError) as e :
        print(f"日付の変換に失敗しました: {e}")
        return None



