FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LAB_DATA=/data LAB_WEB=/app/web
WORKDIR /app
COPY btc-lab/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home lab && mkdir /data && chown lab:lab /data
COPY btc-lab/lab ./lab
COPY lab ./web
USER lab
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3)"
CMD ["python","-m","lab.supervisor"]
