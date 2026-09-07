# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# memeforge server — FastAPI + ffmpeg render pipeline
# Multi-stage: deps (venv) -> runtime (ffmpeg + app).
#
#   production:  docker build -t memeforge-server ./server
#   dev:         same image; docker-compose.dev.yml overrides the command
#                with `uvicorn --reload` + bind-mounts ./server over /app
# ---------------------------------------------------------------------------

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# ---- deps: Python packages in a venv OUTSIDE /app ---------------------------
# (so the dev target can bind-mount source over /app without shadowing
# the installed packages)
FROM base AS deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---- runtime: ffmpeg + app ---------------------------------------------------
FROM base AS runtime
# ffmpeg + ffprobe are REQUIRED for the video render pipeline.
# fonts-dejavu-core: caption/card fallback font when no custom fonts are
# dropped into assets/fonts/ (the compositor falls back to DejaVu Bold).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY app ./app
COPY assets ./assets
COPY tests ./tests
COPY scripts ./scripts
# .dockerignore keeps user clips out of the context; recreate the runtime dirs
# (volumes mount over these in compose).
RUN mkdir -p outputs assets/gameplay assets/sfx assets/fonts \
    && useradd --create-home --shell /usr/sbin/nologin memeforge \
    && chown -R memeforge:memeforge /app
USER memeforge
EXPOSE 8000
# NOTE: exactly one uvicorn worker — render jobs live in an in-memory store,
# so multiple workers would split/lose job state.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
