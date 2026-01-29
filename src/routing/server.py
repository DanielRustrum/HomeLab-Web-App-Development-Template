"""CherryPy server entrypoint for the runtime routing layer."""
from __future__ import annotations

import os

import cherrypy

from routing.endpoints import mount_api
from tsunami.db import init_db


def main() -> None:
    """Configure the database and start the CherryPy engine."""
    app_env = os.getenv("APP_ENV", "prod")
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg://app:app_password@db:5432/homelab_app")

    init_db(
        url=db_url,
        echo=(app_env == "dev"),
        wait=True,
        sync=True,
    )

    cherrypy.config.update({
        "server.socket_host": "0.0.0.0",
        "server.socket_port": int(os.getenv("APP_PORT", "8080")),
        "tools.trailing_slash.on": False,
        "engine.autoreload.on": app_env == "dev",
    })

    mount_api(
        api_root="",
        api_dir=os.getenv("TSUNAMI_ENDPOINT_DIR", "endpoint"),
        pages_dir=os.getenv("TSUNAMI_ROUTING_DIR", "routing"),
        assets_dir=os.getenv("TSUNAMI_ASSETS_DIR", "assets"),
        init_path=os.getenv("TSUNAMI_INIT_PATH", "init.py"),
        run_init=True,
        dev_reload=(app_env == "dev"),
    )

    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":
    main()
