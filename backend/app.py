"""CherryPy entrypoint.

- API is mounted at /api
- In prod, serves the built frontend from ./static (single-container deployment)
- In dev, you usually run Vite separately and proxy /api
"""

from __future__ import annotations

import pathlib, os
import cherrypy
from backend.config import Settings
from backend.routes import Api

def _abs(p: pathlib.Path) -> str:
    return str(p.resolve())

class WebApp:
    """Serves a Vite-built SPA from backend/static.

    Behavior:
    - If the requested file exists in /static, serve it.
    - Otherwise, serve index.html (SPA fallback for deep links).
    """

    def __init__(self, static_dir: pathlib.Path) -> None:
        self.static_dir = static_dir.resolve()

    @cherrypy.expose
    def index(self):
        return cherrypy.lib.static.serve_file(_abs(self.static_dir / "index.html"))

    @cherrypy.expose
    def default(self, *args, **kwargs):
        rel = pathlib.Path(*args) if args else pathlib.Path("index.html")
        candidate = (self.static_dir / rel).resolve()

        # Prevent path traversal
        if self.static_dir not in candidate.parents and candidate != self.static_dir:
            raise cherrypy.HTTPError(404)

        if candidate.is_file():
            return cherrypy.lib.static.serve_file(_abs(candidate))

        # SPA fallback
        return cherrypy.lib.static.serve_file(_abs(self.static_dir / "index.html"))


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
    cherrypy.tree.mount(Api(settings), "/api", config=api_config)

    if has_static:
        cherrypy.tree.mount(WebApp(static_dir), "/", config={"/": {}})

    cherrypy.engine.start()
    cherrypy.engine.block()

if __name__ == "__main__":
    main()
