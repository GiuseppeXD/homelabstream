FROM python:3.12-slim@sha256:4386a385d81dba9f72ed72a6fe4237755d7f5440c84b417650f38336bbc43117

WORKDIR /app

# Install Docker CLI (static binary) for monitoring containers
# Pinning docker-27.3.1 to avoid unexpected CLI changes
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar -xz -C /tmp \
    && cp /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask

COPY app.py /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

ENV MEDIA_DIR=/media
ENV REFRESH_INTERVAL=5
ENV FLASK_APP=app.py

EXPOSE 8989

CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0", "--port=8989"]
