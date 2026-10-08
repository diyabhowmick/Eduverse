# Two stages: build the web app with Node, then run everything on Python.
# The backend serves the built frontend, so one service, one address.

FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim
WORKDIR /app

# opencv-python-headless still needs these two system libraries even though
# "headless" means it has no GUI. Without them the import fails at runtime,
# which is a confusing way to find out.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir "psycopg[binary]" gunicorn

# M1 and the converter are imported by the backend, so they travel with it
COPY backend/ backend/
COPY converter/ converter/
COPY m1/ m1/
# samples/ is deliberately NOT copied. It is a 14MB demo book used only by
# `seed.py --demo`, which is guarded by `if sample.exists()`. Copying it would
# fail the build for anyone whose checkout lacks the folder, and bloat the image.
COPY --from=web /app/frontend/dist frontend/dist

ENV PYTHONPATH=/app/m1:/app/converter \
    FRONTEND_DIST=/app/frontend/dist \
    STORAGE_DIR=/data/storage \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Railway sets PORT. One worker on purpose: M1 holds a lock so only one book
# converts at a time, and a second worker would have its own lock and break that.
CMD ["sh","-c","python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 65"]
