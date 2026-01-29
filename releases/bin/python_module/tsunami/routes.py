"""CherryPy API routes for the template runtime."""
from __future__ import annotations

import json
import cherrypy
from backend.core.config import Settings
from backend.core.db import Database


def _json(body, status=200):
    """Serialize a response body as JSON and set HTTP status."""
    cherrypy.response.status = status
    cherrypy.response.headers["Content-Type"] = "application/json"
        return json.dumps(body).encode("utf-8")


class Api:
    """Root mounted at /api"""

    def __init__(self, settings: Settings) -> None:
        """Create the API handler with configuration and database access."""
        self.settings = settings
        self.db = Database(settings)
        self.health = Health()

    @cherrypy.expose
    def index(self):
        """Return API metadata and advertised endpoints."""
        return _json({
            "name": "homelab-app-template",
            "env": self.settings.app_env,
            "endpoints": ["/api/health"],
        })


class Health:
    """Simple health check endpoint."""
    @cherrypy.expose
    def index(self):
        """Return a basic ok response."""
        return _json({"ok": True})
