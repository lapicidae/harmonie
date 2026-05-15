FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HARMONIE_DATA_DIR=/data \
    HARMONIE_LIBRARIES=/music

# Essentia loads MP3 / M4A / WMA / etc. via FFmpeg.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so the layer cache survives source changes.
COPY pyproject.toml README.md ./
COPY harmonie ./harmonie

# --pre is required because essentia-tensorflow is published with a .dev tag
# (e.g. 2.1b6.devNNNN). pip skips pre-releases without it.
RUN pip install --upgrade pip \
    && pip install --pre .

VOLUME ["/data", "/music"]
EXPOSE 8842

# tini: clean SIGTERM forwarding to uvicorn / worker processes.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["harmonie", "serve"]
