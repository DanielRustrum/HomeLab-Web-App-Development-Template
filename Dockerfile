# ---------- backend dev (no host installs) ----------
FROM python:3.12-slim AS dev-backend

WORKDIR /app

# system deps (psycopg3 binary + build tools if you ever add C deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# install python deps (cached layer)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# NOTE: in dev we bind-mount ./backend into /app/backend (via compose),
# so we do NOT need to COPY backend code here.

EXPOSE 8080
CMD ["python", "-m", "backend.app"]


# ---------- frontend build (prod) ----------
FROM node:20-alpine AS build-frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# ---------- production runtime (serves frontend + api) ----------
FROM python:3.12-slim AS prod

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY --from=build-frontend /frontend/dist /app/backend/static

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python /app/docker/healthcheck.py

CMD ["python", "-m", "backend.app"]
