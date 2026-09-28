# How Rubico runs on a server (Railway, or any Docker host).
# Everything you set up is stored on a volume mounted at /data, so it
# survives updates. See docs/deploy-railway.md.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUBICO_CLOUD=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Rubico listens on $PORT (Railway sets it); /healthz answers without a password.
EXPOSE 8080
CMD ["python", "run.py"]
