"""Serve a built SPA and static assets via CherryPy."""
import cherrypy
import pathlib

def _abs(p: pathlib.Path) -> str:
    """Resolve a filesystem path to an absolute string."""
    return str(p.resolve())

class WebApp:
    """Serves a Vite-built SPA from backend/static.

    Behavior:
    - If the requested file exists in /static, serve it.
    - Otherwise, serve index.html (SPA fallback for deep links).
    """

    def __init__(self, static_dir: pathlib.Path) -> None:
        """Create the web app handler for a directory of static assets."""
        self.static_dir = static_dir.resolve()

    @cherrypy.expose
    def index(self):
        """Serve the SPA entrypoint."""
        return cherrypy.lib.static.serve_file(_abs(self.static_dir / "index.html"))

    @cherrypy.expose
    def default(self, *args, **kwargs):
        """Serve static assets when present, otherwise return the SPA shell."""
        rel = pathlib.Path(*args) if args else pathlib.Path("index.html")
        candidate = (self.static_dir / rel).resolve()

        # Prevent path traversal
        if self.static_dir not in candidate.parents and candidate != self.static_dir:
            raise cherrypy.HTTPError(404)

        if candidate.is_file():
            return cherrypy.lib.static.serve_file(_abs(candidate))

        # SPA fallback
        return cherrypy.lib.static.serve_file(_abs(self.static_dir / "index.html"))
