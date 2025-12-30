"""
Invoice Renamer - PDF請求書ファイル名自動変更ツール

開発環境セットアップに関する注意:
このパッケージは開発モードでのインストールをサポートしています。
`pip install -e .` で開発モードインストールを実行すると、
ソースコードの変更が即座に反映され、再インストール不要で開発が可能です。

詳細な環境構築手順、依存関係はREADME.mdを参照してください。

pyproject.tomlを使用した新しいビルドシステムに移行しました。
setup.pyは後方互換性のために残されています。

Copyright (C) 2023-2025 mrhoge

This file is part of InvoiceRenamer.

InvoiceRenamer is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed WITHOUT ANY WARRANTY; for more details see
the LICENSE file in the distribution root.
"""
from setuptools import setup

# pyproject.tomlから設定を読み込むため、setup()のみを呼び出す
setup()

