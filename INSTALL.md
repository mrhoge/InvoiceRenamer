# インストール手順

## 前提条件

- Python 3.8以上
- pip（Pythonパッケージマネージャー）
- Tesseract OCR（OCR機能を使用する場合）

### Tesseract OCRのインストール

OCR機能を使用するには、Tesseract OCRが必要です。

**Windows:**
1. [Tesseract-OCR Windows版](https://github.com/UB-Mannheim/tesseract/wiki)からインストーラーをダウンロード
2. インストール時に日本語言語データ（jpn.traineddata）を選択
3. 環境変数PATHにTesseractのパスを追加（通常は自動で追加されます）

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-jpn
```

**macOS:**
```bash
brew install tesseract tesseract-lang
```

## インストール方法

### 方法1: 開発モードでインストール（推奨）

開発モードでインストールすると、ソースコードの変更が即座に反映されます。

```bash
# プロジェクトディレクトリに移動
cd InvoiceRenamer

# 依存関係を含めて開発モードでインストール
pip install -e .
```

### 方法2: 依存関係のみインストール

プロジェクトをインストールせず、依存関係のみをインストールする場合：

```bash
# 必要なパッケージをインストール
pip install PySide6>=6.0.0 PyMuPDF>=1.18.0 pdf2image>=1.16.0 pytesseract>=0.3.0 Pillow>=9.0.0
```

この方法の場合、以下のいずれかの方法でプログラムを実行してください：

#### オプションA: PYTHONPATHを設定して実行

**Windows (コマンドプロンプト):**
```cmd
set PYTHONPATH=%CD%\src
python main.py
```

**Windows (PowerShell):**
```powershell
$env:PYTHONPATH="$PWD\src"
python main.py
```

**Linux/macOS:**
```bash
export PYTHONPATH="$PWD/src"
python main.py
```

#### オプションB: 実行スクリプトを使用

プロジェクトに以下のような実行スクリプトを作成することもできます。

**run.bat (Windows用):**
```batch
@echo off
set PYTHONPATH=%~dp0src
python "%~dp0main.py" %*
```

**run.sh (Linux/macOS用):**
```bash
#!/bin/bash
export PYTHONPATH="$(dirname "$0")/src"
python "$(dirname "$0")/main.py" "$@"
```

## 実行方法

### 開発モードでインストールした場合

```bash
# コマンドラインから直接実行
invoice_renamer

# または
python -m invoice_renamer.main
```

### 依存関係のみインストールした場合

上記の「オプションA」または「オプションB」の方法で実行してください。

## トラブルシューティング

### PySide6のインポートエラー

**エラー:** `ModuleNotFoundError: No module named 'PySide6'`

**解決策:**
```bash
pip install PySide6
```

### Tesseractが見つからないエラー

**エラー:** `TesseractNotFoundError`

**解決策:**
1. Tesseract OCRがインストールされているか確認
2. PATHにTesseractのパスが含まれているか確認
3. Windowsの場合、pytesseractの設定でTesseractのパスを明示的に指定：

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### システムライブラリエラー (Linux)

**エラー:** `ImportError: libEGL.so.1: cannot open shared object file`

**解決策:**
```bash
sudo apt-get install libgl1-mesa-glx libegl1-mesa
```

## 開発環境のセットアップ

開発に必要な追加パッケージをインストール：

```bash
pip install -e ".[dev]"
```

これにより、pytest、blackなどの開発ツールがインストールされます。

## 仮想環境の使用（推奨）

プロジェクト専用の仮想環境を作成することを推奨します：

```bash
# 仮想環境を作成
python -m venv venv

# 仮想環境を有効化
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 依存関係をインストール
pip install -e .
```
