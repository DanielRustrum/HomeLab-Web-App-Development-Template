# Backend (CherryPy)

Run locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example .env
python -m backend.app
```

Env options:

- `DATABASE_URL` (preferred for remote DB)
- OR `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

Endpoints:

- `GET /api/health`
- `GET /api/notes`
- `POST /api/notes` JSON `{ "title": "...", "body": "..." }`
