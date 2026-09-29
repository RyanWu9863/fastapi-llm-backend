# slim 版：比完整版小很多，只保留執行 Python 需要的東西
FROM python:3.12-slim

# 不產生 .pyc；輸出不經緩衝，docker logs 才能即時看到 log
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# 先只複製 requirements.txt 再安裝：之後只改程式碼時，這層可以直接用快取，不用重裝套件
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# 不用 root 執行：萬一服務被攻破，攻擊者拿到的權限也有限
RUN useradd --create-home appuser && mkdir /data && chown appuser /data
USER appuser

# 工作目錄設成資料目錄：.env 裡的相對路徑（./app.db、./chroma_data）都會落在 /data，
# 掛一個 volume 到 /data 就能保存資料，容器刪掉重建也不會遺失
WORKDIR /data

EXPOSE 8000
# 讓 Docker 定期打 /health，服務卡死時狀態會變成 unhealthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# fastapi run 是正式模式：不開熱重載，預設監聽 0.0.0.0（容器外面才連得進來）
CMD ["fastapi", "run", "/app/app/main.py", "--port", "8000"]
