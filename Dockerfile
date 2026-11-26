# EduVerse on Railway: one container, backend serves the built frontend.

# ---- 1. build the React frontend ----
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python backend + M1 + converter ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libglib/libgl for OpenCV.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# LibreOffice Draw turns EMF and WMF pictures from Word books into PNG (browsers cannot show EMF or WMF), and opens
# old .doc uploads. About 350 MB. Build with --build-arg OFFICE=0 to leave it out; such pictures then show a
# "could not be converted" box for the reviewer to replace. TIFF and BMP are converted either way.
ARG OFFICE=1
RUN if [ "$OFFICE" = "1" ]; then apt-get update && apt-get install -y --no-install-recommends libreoffice-draw-nogui \
    && rm -rf /var/lib/apt/lists/*; fi

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Eddie's own voice (Kokoro, CPU). Build with --build-arg EDDIE_VOICE=0 to leave it out; the app then uses the phone's voice.
ARG EDDIE_VOICE=1
COPY backend/requirements-voice.txt backend/requirements-voice.txt
COPY scripts/get_voice_model.sh scripts/get_voice_model.sh
RUN if [ "$EDDIE_VOICE" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends ffmpeg curl libsndfile1 && rm -rf /var/lib/apt/lists/* \
      && pip install -r backend/requirements-voice.txt \
      && EDDIE_VOICE_DIR=/app/backend/voice_models sh scripts/get_voice_model.sh; fi

COPY backend/ backend/
COPY m1/ m1/
COPY converter/ converter/
COPY samples/ samples/
COPY --from=web /web/dist frontend/dist

# uploads and converted books; mount a Railway volume here so they survive redeploys
ENV STORAGE_DIR=/data/storage
RUN mkdir -p /data/storage

# Runs as an ordinary user, not root. The container starts as root only to hand a freshly mounted volume
# (Railway, Docker) to that user, then drops to it before any app code runs.
RUN useradd --create-home --uid 10001 eduverse && chown -R eduverse /app /data
COPY scripts/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["sh", "/entrypoint.sh"]

WORKDIR /app/backend
# ROLE=api (default) serves the app; ROLE=worker runs queued background work only (book reading, explanations, papers).
ENV ROLE=api
# WEB_CONCURRENCY web processes: one a CPU core. 2 suits a 2 vCPU box (t3.large, Railway 2 vCPU). Each uses about
# 170 MB and THREADS+8 database connections, so keep WEB_CONCURRENCY x (THREADS + 8) under the database's limit.
ENV WEB_CONCURRENCY=2
CMD ["sh", "-c", "if [ \"$ROLE\" = worker ]; then exec python -m app.worker; else exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'; fi"]
