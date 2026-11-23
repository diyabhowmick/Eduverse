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

# libglib/libgl for OpenCV, LibreOffice is NOT installed (only needed for old .doc uploads)
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

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
COPY --from=web /web/dist frontend/dist

# uploads and converted books; mount a Railway volume here so they survive redeploys
ENV STORAGE_DIR=/data/storage
RUN mkdir -p /data/storage

WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
