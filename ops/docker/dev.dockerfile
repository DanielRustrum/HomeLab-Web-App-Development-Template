# ---------- backend dev (no host installs) ----------
FROM python:3.12-slim AS dev-backend

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# cached deps layer
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

EXPOSE 8080
CMD ["python", "-m", "backend.app"]
