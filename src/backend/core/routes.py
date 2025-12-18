from __future__ import annotations

import json
import cherrypy
from backend.core.config import Settings
from backend.core.db import Database

def _json(body, status=200):
    cherrypy.response.status = status
    cherrypy.response.headers["Content-Type"] = "application/json"
    return json.dumps(body).encode("utf-8")

class Api:
    """Root mounted at /api"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings)
        self.health = Health()
        self.notes = Notes(self.db)

    @cherrypy.expose
    def index(self):
        return _json({
            "name": "homelab-app-template",
            "env": self.settings.app_env,
            "endpoints": ["/api/health", "/api/notes"],
        })

class Health:
    @cherrypy.expose
    def index(self):
        return _json({"ok": True})

class Notes:
    def __init__(self, db: Database) -> None:
        self.db = db

    @cherrypy.expose
    def index(self):
        method = cherrypy.request.method.upper()
        if method == "GET":
            return self._get()
        if method == "POST":
            return self._post()
        raise cherrypy.HTTPError(405)

    def _get(self):
        with self.db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, body, created_at FROM notes ORDER BY created_at DESC LIMIT 200"
                )
                rows = cur.fetchall()
        notes = [
            {"id": r[0], "title": r[1], "body": r[2], "created_at": r[3].isoformat()}
            for r in rows
        ]
        return _json(notes)

    def _post(self):
        try:
            raw = cherrypy.request.body.read() or b"{}"
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return _json({"error": "invalid json"}, status=400)

        if not isinstance(payload, dict):
            return _json({"error": "json body must be an object"}, status=400)

        title = (payload.get("title") or "").strip()
        body = (payload.get("body") or "").strip()
        if not title:
            return _json({"error": "title is required"}, status=400)

        with self.db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO notes (title, body) VALUES (%s, %s) RETURNING id, created_at",
                    (title, body),
                )
                new_id, created_at = cur.fetchone()
                conn.commit()

        return _json({"id": new_id, "title": title, "body": body, "created_at": created_at.isoformat()}, status=201)
