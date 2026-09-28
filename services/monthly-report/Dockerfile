FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
ENV MONTHLY_REPORT_DATA_DIR=/data \
    MONTHLY_REPORT_CONFIG=/config/projects.json
RUN useradd -r -u 10003 monthly && mkdir -p /data && chown monthly /data
USER monthly
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
