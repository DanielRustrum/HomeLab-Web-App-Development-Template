# Homelab App Template (CherryPy + Postgres + Vite PWA)

Template repo for building small homelab apps with:

- **Backend:** Python + CherryPy + PostgreSQL (psycopg3)
- **Frontend:** Vite + React + TypeScript + Tailwind + shadcn/ui
- **PWA:** installable on mobile (offline shell)
- **Deployment:** Docker image + Docker Compose / Portainer Stack
- **DB:** local Postgres in dev, or point at an existing remote Postgres

## Repo layout

```text
.
├─ docs/                 # CherryPy API + static hosting (prod)
├─ ops/                # Vite React PWA + shadcn/ui
├─ src/                      # SQL init + optional helpers
├─ wiki/                  # entrypoint + healthcheck scripts
├─ compose.yaml             # dev compose (db + app + optional frontend)
├─ compose.prod.yaml        # prod compose (app image + external/optional db)
└─ Dockerfile               # multi-stage build (frontend -> backend)
```

## Quick start (development)

### 1) Start a local Postgres (Docker)
```bash
docker compose up -d db
```

### 2) Backend (host machine)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example .env
python -m backend.app
```

Backend runs at: `http://localhost:8080`  
API base: `http://localhost:8080/api`

### 3) Frontend (host machine)
```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: `http://localhost:5173` (proxies `/api` to backend)

## Quick start (all-in-docker dev)

This runs Postgres + backend + Vite dev server in containers:

```bash
docker compose --profile ui up --build
```

- UI: `http://localhost:5173`
- API: `http://localhost:8080/api`
- Postgres: `localhost:5432`

## Production build (single image)

Build the image:

```bash
docker build -t homelab-app:latest .
```

Run with compose (includes optional db):

```bash
docker compose -f compose.prod.yaml up -d
```

- App: `http://localhost:8080` (serves the built frontend + API)

## Pointing to an existing Postgres on another machine

Set **either** `DATABASE_URL` **or** the `DB_*` variables.

Example `.env`:
```bash
DATABASE_URL=postgresql://app:app_password@192.168.3.20:5432/homelab_app
```

Then run the app container (and do *not* run the local `db` service):
```bash
docker compose -f compose.prod.yaml up -d app
```

## Notes

- The backend serves the built frontend from `backend/static/` in production.
- Vite PWA service worker caches the app shell for offline use.
- This template includes a tiny example “Notes” CRUD to verify DB + API + UI.

## License
GNU GENERAL PUBLIC LICENSE


## Flatpak Issues
mkdir -p ~/.var/app/com.visualstudio.code/data/node_modules/bin

cat <<'EOF' | tee ~/.var/app/com.visualstudio.code/data/node_modules/bin/docker >/dev/null
#!/usr/bin/env sh
exec flatpak-spawn --host docker "$@"
EOF

chmod +x ~/.var/app/com.visualstudio.code/data/node_modules/bin/docker