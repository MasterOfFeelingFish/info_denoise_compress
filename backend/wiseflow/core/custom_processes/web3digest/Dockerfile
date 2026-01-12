FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制 WiseFlow 项目（假设在上级目录）
COPY . /app/wiseflow

# 复制 Web3Digest 应用
COPY core/custom_processes/web3digest/requirements.txt /app/web3digest-requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r /app/web3digest-requirements.txt

# 设置环境变量
ENV PYTHONPATH=/app/wiseflow
ENV PYTHONUNBUFFERED=1

# 创建数据目录
RUN mkdir -p /app/data/web3digest/logs

# 运行应用
WORKDIR /app/wiseflow
CMD ["python", "core/custom_processes/web3digest/main.py"]
