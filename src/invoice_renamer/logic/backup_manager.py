"""
バックアップ管理モジュール

PDFファイルのバックアップと一時作業ディレクトリの管理を行う。

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
import shutil
from typing import List
from invoice_renamer.utils import constants

class BackupManager:
    """PDFファイルのバックアップを管理するクラス

    処理開始前のPDFファイルをバックアップし、
    一時作業用ディレクトリを管理する。

    Attributes:
        base_directory (str): 基準ディレクトリ
        work_directory (str): 一時作業用ディレクトリのパス
        pdf_files (List[str]): PDFファイルのリスト
    """

    def __init__(self, base_directory: str):
        """BackupManagerを初期化

        Args:
            base_directory (str): PDFファイルが格納されているディレクトリ
        """
        self.base_directory = base_directory
        self.work_directory = os.path.join(base_directory, constants.WORK_FOLDER_NAME)
        self.pdf_files = self.get_pdf_files(base_directory)


def create_temp_files(base_directory):
    """一時作業用のデータをコピーするラップ関数

    Args:
        base_directory (str): 基準ディレクトリ

    Note:
        一時作業用ディレクトリを作成し、PDFファイルをコピーする
    """
    # 一時作業用ディレクトリを指定
    work_directory_path = os.path.join(base_directory, constants.WORK_FOLDER_NAME)

    # 一時作業用ディレクトリ作成
    make_work_dir(work_directory_path)

    # PDF一覧を参照してコピーを実施
    copy_pdfs_to_work_folder(base_directory, work_directory_path)


def get_pdf_files(base_directory):
    """指定ディレクトリ内のPDFファイルをすべて取得

    Args:
        base_directory (str): 検索対象のディレクトリ

    Returns:
        List[str]: PDFファイル名のリスト
    """
    return [f for f in os.listdir(base_directory) if f.endswith(constants.FILE_EXTENTION_NAME)]


def make_work_dir(temp_directory_path):
    """一時作業用フォルダを作成

    Args:
        temp_directory_path (str): 作成するディレクトリのパス

    Note:
        既に存在する場合は何もしない（exist_ok=True）
    """
    try:
        os.makedirs(temp_directory_path,exist_ok=True)
        print(f"フォルダ '{temp_directory_path}' を作成しました。")
    except Exception as e:
        print(f"フォルダを作成できませんでした: {e}")


def copy_pdfs_to_work_folder(base_directory, copy_to_directory):
    """PDFの作業用コピーを作成

    Args:
        base_directory (str): コピー元のディレクトリ
        copy_to_directory (str): コピー先のディレクトリ

    Note:
        すべてのPDFファイルを作業用フォルダにコピーする
    """
    # コピー対象のPDF一覧を取得
    pdf_files = get_pdf_files(base_directory)

    # PDF一覧をもとに、ファイルを作業用フォルダにコピー
    for pdf_file in pdf_files:
        source_path = os.path.join(base_directory, pdf_file)
        copy_to_path = os.path.join(base_directory, constants.WORK_FOLDER_NAME, pdf_file)

        try:
            shutil.copy2(source_path, copy_to_directory)
            print(f"ファイル '{pdf_file}' を '{copy_to_directory}' にコピーしました。")
        except Exception as e:
            print(f"ファイル '{pdf_file}' をコピーできませんでした: {e}")


