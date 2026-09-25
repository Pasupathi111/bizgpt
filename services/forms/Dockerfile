# ---- build the React form page ----
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
ENV FORMS_CONFIG_DIR=/config/forms \
    FORMS_DB_PATH=/data/forms.db \
    FORMS_WEB_DIST=/srv/web/dist
RUN useradd -r -u 10001 forms && mkdir -p /data && chown forms /data
USER forms
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
