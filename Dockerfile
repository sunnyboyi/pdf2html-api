FROM pdf2htmlex/pdf2htmlex:0.18.8.rc2-master-20200820-ubuntu-20.04-x86_64

# 安装 Python 和 pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app.py .

# 创建临时目录
RUN mkdir -p /tmp/pdf2html

EXPOSE 5000

# 重置入口点，使用 gunicorn 运行
ENTRYPOINT []
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "app:app"]
