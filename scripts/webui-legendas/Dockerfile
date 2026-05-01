FROM python:3.12-slim@sha256:46cb7cc2877e60fbd5e21a9ae6115c30ace7a077b9f8772da879e4590c18c2e3

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates ffmpeg \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar -xz -C /tmp \
    && cp /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py config.py db.py jobs.py scanner.py watcher.py translate.py extractor.py docker_utils.py /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

ENV MEDIA_DIR=/media
ENV OLLAMA_URL=http://ollama:11434/api/generate
ENV TRANSLATE_MODEL=gemma3:4b
ENV REFRESH_INTERVAL=15

EXPOSE 8989

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8989"]
