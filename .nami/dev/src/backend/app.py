from __future__ import annotations

import os
import pathlib
import cherrypy

from backend.core.config import Settings
from backend.core.endpoints import mount_api
from backend.core.web import WebApp
from backend.core.db import init_db, schema  # schema only if you want the optional sync_all

def main() -> None:
    APP_ENV = os.getenv("APP_ENV", "prod")

    # IMPORTANT: in Docker, host should be the service name (e.g. db), not localhost
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://app:app_password@db:5432/homelab_app")

    # init_db does: create engine -> bind -> wait -> sync_all (by default)
    init_db(
        url=db_url,
        echo=(APP_ENV == "dev"),
        wait=True,
        sync=True,
    )

    static_dir = pathlib.Path(__file__).parent / "static"
    if (static_dir / "index.html").exists():
        cherrypy.tree.mount(WebApp(static_dir), "/", config={"/": {}})

    cherrypy.config.update({
        "server.socket_host": "0.0.0.0",
        "server.socket_port": int(os.getenv("APP_PORT", "8080")),
        "tools.trailing_slash.on": False,
        "engine.autoreload.on": APP_ENV == "dev",
    })

    # Mount API after DB is bound; any dynamically imported @table will auto-create tables.
    mount_api(api_root="/api", api_dir="api")

    # Optional: belt+suspenders (idempotent). If you don't want app.py touching schema, remove this.
    # from backend.core.db import get_db
    # schema.sync_all(get_db().engine)

    cherrypy.engine.start()
    cherrypy.engine.block()

if __name__ == "__main__":
    main()
