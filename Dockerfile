# ベースとなるPythonの公式イメージ（Pythonのバージョンは適宜変更）
FROM python:3.13-slim
# FROM python:3.13 #こっちはイメージサイズ削減のため使わない

# 作業ディレクトリを設定
WORKDIR /app

# OSレベルのライブラリをインストール_これらはPyQt/PySideを使うために必要
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-shape0 \
    libegl1 \
    libopengl0 \
    libgles2 \
    libfontconfig1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 必要なファイルをコンテナにコピー
COPY requirements.txt .

# ライブラリをインストール
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコードをコピー。GitHubからソースを取得する場合はコメントアウトする
# COPY . .

# PYTHONPATHを設定して、アプリケーションのディレクトリをPythonのimportパスに追加
ENV PYTHONPATH=/app/src

# エントリーポイント（変更が必要なら適宜修正・ただしdocker run コマンドで上書き可能）
# CMD ["python", "main.py"]
