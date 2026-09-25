# ---- build the dashboard UI ----
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- API ----
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY --from=web /web/dist web/dist
ENV WORKFLOWS_CONFIG_PATH=/config/workflows.yaml \
    API_DB_PATH=/data/api.db \
    API_WEB_DIST=/srv/web/dist
RUN useradd -r -u 10003 bizgptapi && mkdir -p /data && chown bizgptapi /data
USER bizgptapi
EXPOSE 8003
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8003/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--proxy-headers"]
