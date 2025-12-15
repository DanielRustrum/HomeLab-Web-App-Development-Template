# syntax=docker/dockerfile:1

ARG NODE_VERSION=20
ARG PYTHON_VERSION=3.12

# ---------- frontend build ----------
FROM node:${NODE_VERSION}-alpine AS frontend-build
WORKDIR /frontend

# deps first (better caching)
COPY src/frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# build
COPY src/frontend/ ./
RUN npm run build

# ---------- backend runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# install python deps
COPY src/backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# copy backend source
COPY src/backend/ /app/backend/

# copy built frontend into backend/static (served in prod)
COPY --from=frontend-build /frontend/dist/ /app/backend/static/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health').read()"

CMD ["python", "-m", "backend.app"]
