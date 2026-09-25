FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

RUN useradd -r -u 10003 integrations
USER integrations

EXPOSE 8002
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8002/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--proxy-headers"]
