@echo off
REM Invoice Renamer 実行スクリプト (Windows用)
REM このスクリプトはPYTHONPATHを設定してmain.pyを実行します

REM スクリプトのディレクトリを取得
set SCRIPT_DIR=%~dp0

REM PYTHONPATHにsrcディレクトリを追加
set PYTHONPATH=%SCRIPT_DIR%src

REM main.pyを実行
python "%SCRIPT_DIR%main.py" %*

REM エラーが発生した場合は一時停止
if errorlevel 1 pause
