"""CherryPy entrypoint.

- API is mounted at /api
- In prod, serves the built frontend from ./static (single-container deployment)
- In dev, you usually run Vite separately and proxy /api
"""

from __future__ import annotations

import pathlib, os
import cherrypy
from backend.core.config import Settings
from backend.core.endpoints import mount_api
from backend.core.web import WebApp


def main() -> None:
    settings = Settings()

    static_dir = pathlib.Path(__file__).parent / "static"
    has_static = (static_dir / "index.html").exists()

    APP_ENV = os.getenv("APP_ENV", "prod")

    cherrypy.config.update({
        "server.socket_host": "0.0.0.0",
        "server.socket_port": int(os.getenv("APP_PORT", "8080")),
        "tools.trailing_slash.on": False,
        "engine.autoreload.on": APP_ENV == "dev",
    })


    api_config = {
        "/": {
            "tools.encode.on": True,
            "tools.encode.encoding": "utf-8",
        }
    }

    if has_static:
        cherrypy.tree.mount(WebApp(static_dir), "/", config={"/": {}})

    mount_api(api_root="/api", api_dir="api")
    cherrypy.engine.start()
    cherrypy.engine.block()

if __name__ == "__main__":
    main()
