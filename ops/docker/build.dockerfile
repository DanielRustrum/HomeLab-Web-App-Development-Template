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

# IMPORTANT: healthcheck references /app/docker/healthcheck.py
# so make sure it exists in the image:
COPY docker /app/docker

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python /app/docker/healthcheck.py

CMD ["python", "-m", "backend.app"]
