FROM python:3.12-slim@sha256:46cb7cc2877e60fbd5e21a9ae6115c30ace7a077b9f8772da879e4590c18c2e3

WORKDIR /app

# Install Docker CLI (static binary) for monitoring containers
# Pinning docker-27.3.1 to avoid unexpected CLI changes
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar -xz -C /tmp \
    && cp /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask watchdog requests

COPY app.py /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

ENV MEDIA_DIR=/media
ENV BAZARR_LOG_DIR=/bazarr-logs
ENV OLLAMA_URL=http://ollama:11434/api/generate
ENV TRANSLATE_MODEL=qwen2.5:7b
ENV REFRESH_INTERVAL=15
ENV FLASK_APP=app.py

EXPOSE 8989

CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0", "--port=8989"]
