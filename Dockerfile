FROM docker.m.daocloud.io/library/python:3.10-slim

WORKDIR /app

# 先复制依赖清单并安装，利用 Docker 缓存加速构建1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制当前目录下所有拆分后的代码和静态文件
COPY . .

# 暴露 5000 端口
EXPOSE 5000

# 将启动入口修改为 main.py
CMD ["python", "main.py"]
