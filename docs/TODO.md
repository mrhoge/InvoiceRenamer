# TODO: 実装予定機能

## ?? 高優先度

---

## ?? 中優先度

### CI/CD自動ビルド・リリース

- [ ] **GitHub Actions による自動ビルド**
  - Push/タグをトリガーにWindows/Mac用の実行可能ファイルを自動ビルド
  - PyInstallerまたはbriefcaseを使用したビルドワークフロー作成

**実装内容**:

1. **GitHub Actions ワークフロー作成**
   - ファイル: `.github/workflows/build-release.yml`
   - トリガー: `push` (tags: `v*.*.*`) または手動実行 (`workflow_dispatch`)

2. **ビルド対象プラットフォーム**
   - **Windows**: `.exe` (PyInstaller/briefcase)
   - **macOS**: `.app` または `.dmg` (PyInstaller/briefcase)
   - 将来的には Linux `.AppImage` も検討可能

3. **ビルドツール選定**
   - **PyInstaller**: シンプル、実績豊富、細かい制御可能
   - **briefcase**: BeeWare公式、モダン、クロスプラットフォーム対応
   - 推奨: 初期実装はPyInstaller、将来的にbriefcase移行を検討

4. **リリース自動化**
   - ビルド成果物をGitHub Releasesに自動アップロード
   - リリースノートの自動生成（コミットメッセージから）
   - バージョニング: `pyproject.toml` のバージョンを使用

5. **依存関係の処理**
   - Tesseract OCRのバンドル方法（インストーラーに同梱 or ユーザーインストール要求）
   - Qt/PySide6のバンドル（PyInstallerで自動処理）
   - ライセンスファイル（LICENSE, NOTICE, COPYRIGHT）の同梱

**実装例（GitHub Actions）**:
```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*.*.*'
  workflow_dispatch:

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pyinstaller
      - name: Build executable
        run: pyinstaller invoice_renamer.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: InvoiceRenamer-Windows
          path: dist/InvoiceRenamer.exe

  build-macos:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -e .
          pip install pyinstaller
      - name: Build app
        run: pyinstaller invoice_renamer.spec
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: InvoiceRenamer-macOS
          path: dist/InvoiceRenamer.app

  release:
    needs: [build-windows, build-macos]
    runs-on: ubuntu-latest
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v3
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            InvoiceRenamer-Windows/*
            InvoiceRenamer-macOS/*
          generate_release_notes: true
```

**PyInstaller設定例（invoice_renamer.spec）**:
```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/invoice_renamer/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.toml', '.'),
        ('LICENSE', '.'),
        ('NOTICE', '.'),
        ('COPYRIGHT', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='InvoiceRenamer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'  # アイコンファイルを用意する場合
)
```

**実装時間**: 4-8時間
**ファイル数**: 2-3ファイル (ワークフロー、spec、ドキュメント)

**メリット**:
- ユーザーがPython環境不要で使用可能
- リリースプロセスの自動化・効率化
- バージョン管理とビルドの紐付け
- 配布の簡便化

**注意点**:
- Tesseract OCRの同梱方法を検討（ライセンス確認必要）
- macOSのコード署名（Apple Developer Program必要、$99/年）
- Windowsのコード署名（オプション、信頼性向上）

---

### 機能改善

---

#### 設定画面UI（中規模実装）

**概要**:
- config.tomlの設定項目を画面上で確認・変更できるUIを実装する。

**実装規模**:
- **実装時間**: 4-6時間
- **ファイル数**: 2-3ファイル
- **推奨度**: 中

**実装内容**:

1. **設定ダイアログ（タブ分け）**
   - **OCR設定タブ**:
     - Y座標許容誤差 (QDoubleSpinBox: 0.5～10.0)
     - OCR言語 (QComboBox: jpn+eng, jpn, eng)

   - **PDF設定タブ**:
     - PDFハンドラー (QComboBox: pymupdf, pdf2image)
     - キャッシュサイズ (QLineEdit + 単位選択)

   - **ログ設定タブ**:
     - コンソールレベル (QComboBox: DEBUG, INFO, WARNING, ERROR)
     - ファイルレベル (QComboBox: DEBUG, INFO, WARNING, ERROR)
     - ログディレクトリ (QLineEdit + 参照ボタン)

2. **機能**
   - リアルタイムバリデーション（入力値の検証）
   - デフォルト値への復元ボタン
   - 設定プレビュー（変更前/後の比較）
   - 不正な値の入力防止

3. **統合**
   - メニューバーに「設定」メニュー追加
   - ConfigManagerの拡張（設定保存メソッド追加）

**実装ファイル**:
```
src/invoice_renamer/ui/settings_dialog.py  (新規作成)
src/invoice_renamer/logic/config_manager.py  (拡張)
```

**メリット**:
- ユーザーフレンドリー（手動でTOML編集不要）
- 拡張性が高い（将来的な設定項目追加が容易）
- エラー防止機能が充実（バリデーション、範囲チェック）

---

### 設定の永続化
- [ ] OCR言語設定の保存・復元
- [ ] デバッグモード状態の記憶
- [ ] ウィンドウサイズ・位置の保存

---

## ?? 低優先度

### OCRテキスト抽出精度の向上
- [ ] 画像前処理アルゴリズムの最適化
- [ ] 異なる解像度・品質のPDFでの精度テスト
- [ ] ノイズ除去フィルターの追加

### 座標変換の単体テストケースの追加
- [ ] 様々なズーム倍率での座標変換テスト
- [ ] 境界値テストケースの作成
- [ ] 回帰テスト用のテストスイート構築

### パフォーマンス最適化
- [ ] 大きなPDFファイルの処理速度向上
- [ ] メモリ使用量の最適化
- [ ] OCR処理の並列化

### ユーザビリティ向上
- [ ] キーボードショートカットの追加
- [ ] ドラッグ&ドロップ対応
- [ ] プログレスバーの表示

---

## 関連ファイル

- `src/invoice_renamer/ui/pdf_viewer.py` - メインUI・座標変換ロジック
- `src/invoice_renamer/logic/selection_analyzer_v6.py` - 選択範囲分析・OCR処理
- `src/invoice_renamer/logic/pdf_handlers.py` - PDF読み込み・レンダリング
- `src/invoice_renamer/logic/config_manager.py` - 設定管理
- `config.toml` - アプリケーション設定ファイル
- `LICENSE` - GPL-3.0ライセンス全文
- `NOTICE` - サードパーティライブラリのライセンス通知
- `LICENSE.md` - ライセンス情報（日本語）
- `COPYRIGHT` - 著作権者情報（要作成）

---

## 補足

- 各機能の実装は独立しているため、優先度の高いものから順次実装可能。
- エラーハンドリングは既存の `ErrorHandler` クラスを活用することで実装コストを削減できる。
- 処理結果サマリーは、UI側（QMessageBox）でも表示可能。

---

## 進捗管理

作業開始時は `[ ]` を `[x]` に変更してください。
各タスクの詳細メモや発見事項はこのファイルに追記してください。

---

**作成日**: 2025-12-01
**最終更新**: 2025-12-30
**整理**: Claude Code
