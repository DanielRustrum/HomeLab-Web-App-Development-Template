"""Dynamic endpoint/router loader for CherryPy-backed APIs and pages."""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import typing as t
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import ModuleType
import os


import cherrypy
from typing import Any, Callable

_MODULE_CACHE: dict[str, tuple[float, ModuleType]] = {}

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
_ALREADY_MOUNTED = False
_INIT_ALREADY_RUN = False


def _find_src_root(start: Path) -> Path:
    """Walk parents to locate the src root by markers or fallback."""
    for parent in [start] + list(start.parents):
        if (parent / "endpoint").exists() or (parent / "routing").exists():
            return parent
        if parent.name == "src":
            return parent
    return start.parents[2]


_SRC_ROOT = _find_src_root(Path(__file__).resolve().parent)
_DEFAULT_ENDPOINT_DIR = _SRC_ROOT / "endpoint"
_DEFAULT_PAGES_DIR = _SRC_ROOT / "routing"
_DEFAULT_ASSETS_DIR = _SRC_ROOT / "assets"
_DEFAULT_INIT_PATH = _SRC_ROOT / "init.py"


class Endpoint:
    """Base class for endpoint modules: class Endpoint(endpoints.Endpoint)."""

    def init(self) -> None:
        """Hook called before each request handler."""
        ...

    def auth(self) -> None:
        """Hook for auth/authorization checks before handler execution."""
        ...

    def cleanup(self) -> None:
        """Hook called after each request handler, even on errors."""
        ...

    def _run(self, method: str, route_params: dict[str, str]) -> t.Any:
        """Invoke a method with request/route-bound parameters."""
        self.init()
        try:
            self.auth()
            fn = getattr(self, method, None)
            if not callable(fn):
                raise cherrypy.HTTPError(405, "Method Not Allowed")
            return _call_with_binding(fn, route_params)
        finally:
            try:
                self.cleanup()
            except Exception:
                pass



def params(spec: dict[str, Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Annotate endpoint methods with explicit query parameter metadata."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        """Return the function unchanged while carrying metadata."""
        return fn
    return deco


def _run_init_file(init_path: str | Path | None) -> None:
    """Execute the optional init.py module once per process."""
    global _INIT_ALREADY_RUN
    if _INIT_ALREADY_RUN:
        return

    path = Path(init_path) if init_path is not None else _DEFAULT_INIT_PATH
    if not path.exists():
        _INIT_ALREADY_RUN = True
        return

    spec = importlib.util.spec_from_file_location("tsunami_init", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load init module from {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["tsunami_init"] = module
    spec.loader.exec_module(module)
    _INIT_ALREADY_RUN = True










def mount_api(
    *,
    api_root: str = "",
    api_dir: str | Path | None = None,
    pages_dir: str | Path | None = None,
    assets_dir: str | Path | None = None,
    init_path: str | Path | None = None,
    run_init: bool = True,
    dev_reload: bool = False,
) -> None:
    """
    Mount the dynamic API/router tree and optional pages/assets handlers.

    Filename rules:
      notes.py             -> /notes
      notes.[id].py        -> /notes/<id>
      admin/users.py       -> /admin/users
      admin/users.[uid].py -> /admin/users/<uid>
      index.py             -> /
    """
    global _ALREADY_MOUNTED
    if _ALREADY_MOUNTED:
        return

    if api_dir is None:
        api_dir_path = _DEFAULT_ENDPOINT_DIR
    else:
        api_dir_path = Path(api_dir)
        if not api_dir_path.is_absolute():
            cwd_path = Path.cwd() / api_dir_path
            api_dir_path = cwd_path if cwd_path.exists() else _SRC_ROOT / api_dir_path

    if pages_dir is None:
        pages_dir_path = _DEFAULT_PAGES_DIR
    else:
        pages_dir_path = Path(pages_dir)
        if not pages_dir_path.is_absolute():
            cwd_path = Path.cwd() / pages_dir_path
            pages_dir_path = cwd_path if cwd_path.exists() else _SRC_ROOT / pages_dir_path

    if assets_dir is None:
        assets_dir_path = _DEFAULT_ASSETS_DIR
    else:
        assets_dir_path = Path(assets_dir)
        if not assets_dir_path.is_absolute():
            cwd_path = Path.cwd() / assets_dir_path
            assets_dir_path = cwd_path if cwd_path.exists() else _SRC_ROOT / assets_dir_path

    if run_init:
        _run_init_file(init_path)

    router = ApiRouter(
        api_dir=api_dir_path,
        pages_dir=pages_dir_path,
        assets_dir=assets_dir_path,
        dev_reload=dev_reload,
    )
    mount_path = "/" + api_root.strip("/")
    cherrypy.tree.mount(router, mount_path)

    _ALREADY_MOUNTED = True


class ApiRouter:
    """
    Mounted at /api. Uses default() to catch /api/* and dispatches to files in backend/api.
    """

    def __init__(
        self,
        *,
        api_dir: Path,
        pages_dir: Path,
        assets_dir: Path,
        dev_reload: bool = False,
    ) -> None:
        """Create a router with endpoint, page, and asset roots."""
        self.api_dir = Path(api_dir).resolve()
        self.pages_dir = Path(pages_dir).resolve()
        self.assets_dir = Path(assets_dir).resolve()
        self._dev_reload = dev_reload
        self._routes = _build_route_table(self.api_dir)
        self._page_routes, self._not_found_page = _build_pages_route_table(self.pages_dir)
        self._endpoint_cache: dict[Path, type[Endpoint]] = {}
        self._manifest_cache: dict[str, Any] | None = None
        self._manifest_mtime: int | None = None
        self._routes_mtime = _dir_mtime(self.api_dir, suffixes={".py"})
        self._pages_mtime = _dir_mtime(self.pages_dir, suffixes={".tsx"})

    @cherrypy.expose
    def index(self):
        """Serve the root path or TSX index page when available."""
        # /
        self._maybe_refresh_routes()
        if cherrypy.request.method and cherrypy.request.method.upper() not in {"GET", "HEAD"}:
            raise cherrypy.HTTPError(405)

        page_match = _match_route(self._page_routes, [])
        if page_match is not None:
            return self._serve_page(page_match["file"], status=200)

        return _serialize({"ok": True})

    @cherrypy.expose
    def __routes(self):
        """Return a debug list of discovered API routes."""
        # /api/__routes  (debug)
        self._maybe_refresh_routes()
        return _serialize(
            {
                "api_dir": str(self.api_dir),
                "routes": [r["pattern"] for r in self._routes],
            }
        )

    @cherrypy.expose
    def default(self, *vpath, **_params):
        """Dispatch requests to assets, pages, or API endpoints."""
        # /<anything...> (API also available under /api/*)
        self._maybe_refresh_routes()
        segments = [s for s in vpath if s]
        if segments and segments[0] == "api":
            api_segments = segments[1:]
            if not api_segments:
                return _serialize(
                    {
                        "api_dir": str(self.api_dir),
                        "routes": [r["pattern"] for r in self._routes],
                    }
                )
            if len(api_segments) == 1 and api_segments[0] == "__routes":
                return _serialize(
                    {
                        "api_dir": str(self.api_dir),
                        "routes": [r["pattern"] for r in self._routes],
                    }
                )
            method = (cherrypy.request.method or "GET").lower()
            if method not in _HTTP_METHODS:
                raise cherrypy.HTTPError(405)

            match = _match_route(self._routes, api_segments)
            if match is not None:
                endpoint_cls = self._load_endpoint_cls(match["file"])
                ep: Endpoint = endpoint_cls()
                result = ep._run(method, match["params"])
                return _serialize(result)

            cherrypy.response.status = 404
            return _serialize({"error": "No matching route"})

        if segments and segments[0] == "assets":
            return self._serve_asset(segments[1:])
        method = (cherrypy.request.method or "GET").lower()
        if method not in _HTTP_METHODS:
            raise cherrypy.HTTPError(405)

        if method in {"get", "head"}:
            page_match = _match_route(self._page_routes, segments)
            endpoint_match = _match_route(self._routes, segments)

            if page_match is not None:
                if endpoint_match is not None:
                    endpoint_cls = self._load_endpoint_cls(endpoint_match["file"])
                    if callable(getattr(endpoint_cls, "get", None)):
                        raise cherrypy.HTTPError(500, "TSX route takes precedence over GET endpoint.")
                return self._serve_page(page_match["file"], status=200)

            if endpoint_match is not None:
                endpoint_cls = self._load_endpoint_cls(endpoint_match["file"])
                ep: Endpoint = endpoint_cls()
                result = ep._run(method, endpoint_match["params"])
                return _serialize(result)

            if self._not_found_page:
                return self._serve_page(self._not_found_page, status=404)

            raise cherrypy.HTTPError(404, "No matching route")

        match = _match_route(self._routes, segments)
        if match is None:
            raise cherrypy.HTTPError(404, "No matching endpoint")

        endpoint_cls = self._load_endpoint_cls(match["file"])
        ep: Endpoint = endpoint_cls()
        result = ep._run(method, match["params"])
        return _serialize(result)

    def _load_endpoint_cls(self, file_path: Path) -> type[Endpoint]:
        """Load and cache the Endpoint class for a module path."""
        cached = self._endpoint_cache.get(file_path)
        if cached is not None:
            return cached


        mod = _load_module_from_file(file_path, api_dir=self.api_dir)
        endpoint_cls = getattr(mod, "Endpoint", None)
        if endpoint_cls is None or not inspect.isclass(endpoint_cls):
            raise cherrypy.HTTPError(500, f"{file_path.name} must export class Endpoint")

        self._endpoint_cache[file_path] = endpoint_cls
        return endpoint_cls

    def _tsx_route_exists(self, file_path: Path) -> bool:
        """Check if a TSX page exists for a matching endpoint path."""
        if not self.pages_dir.exists():
            return False
        try:
            rel = file_path.relative_to(self.api_dir)
        except ValueError:
            return False
        tsx_path = (self.pages_dir / rel).with_suffix(".tsx")
        return tsx_path.exists()

    def _serve_page(self, page_path: Path, *, status: int) -> str:
        """Render a minimal HTML shell for a TSX page route."""
        manifest = self._load_manifest()
        rel = page_path.relative_to(self.pages_dir).as_posix()
        key = rel[:-4] if rel.endswith(".tsx") else rel

        entry = _resolve_manifest_entry(manifest, key, rel)
        if entry is None:
            raise cherrypy.HTTPError(500, f"Missing manifest entry for {key}")

        scripts = _collect_js_assets(manifest, entry)
        css_files = [css for css in entry.get("css", []) if isinstance(css, str)]

        html_lines: list[str] = [
            "<!doctype html>",
            "<html>",
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            f"<title>{key}</title>",
        ]

        for css in css_files:
            css_path = css.removeprefix("assets/")
            html_lines.append(f'<link rel="stylesheet" href="/assets/{css_path}">')

        html_lines.append("</head>")
        html_lines.append("<body>")
        html_lines.append('<div id="app"></div>')

        for script in scripts:
            if script:
                script_path = script.removeprefix("assets/")
                html_lines.append(f'<script type="module" src="/assets/{script_path}"></script>')

        html_lines.append("</body>")
        html_lines.append("</html>")

        cherrypy.response.status = status
        cherrypy.response.headers["Content-Type"] = "text/html; charset=utf-8"
        return "\n".join(html_lines)

    def _load_manifest(self) -> dict[str, Any]:
        """Load the Vite manifest used to resolve built assets."""
        manifest_path = _resolve_manifest_path(self.assets_dir)
        if manifest_path is None:
            raise cherrypy.HTTPError(500, f"Missing manifest in {self.assets_dir}")

        if self._manifest_cache is not None:
            if not self._dev_reload:
                return self._manifest_cache
            mtime = manifest_path.stat().st_mtime_ns
            if self._manifest_mtime == mtime:
                return self._manifest_cache

        self._manifest_cache = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._manifest_mtime = manifest_path.stat().st_mtime_ns
        return self._manifest_cache

    def _maybe_refresh_routes(self) -> None:
        """Rebuild route tables when files change in dev mode."""
        if not self._dev_reload:
            return

        routes_mtime = _dir_mtime(self.api_dir, suffixes={".py"})
        pages_mtime = _dir_mtime(self.pages_dir, suffixes={".tsx"})
        if routes_mtime == self._routes_mtime and pages_mtime == self._pages_mtime:
            return

        self._routes = _build_route_table(self.api_dir)
        self._page_routes, self._not_found_page = _build_pages_route_table(self.pages_dir)
        self._routes_mtime = routes_mtime
        self._pages_mtime = pages_mtime
        self._manifest_cache = None
        self._manifest_mtime = None

    def _serve_asset(self, segments: list[str]) -> Any:
        """Serve a static asset from the configured assets directory."""
        rel = Path(*segments) if segments else Path()
        candidate = (self.assets_dir / rel).resolve()

        if self.assets_dir not in candidate.parents and candidate != self.assets_dir:
            raise cherrypy.HTTPError(404)

        if not candidate.is_file():
            raise cherrypy.HTTPError(404)

        return cherrypy.lib.static.serve_file(str(candidate))


def _build_route_table(api_dir: Path) -> list[dict[str, t.Any]]:
    """Scan endpoint files and build a sorted routing table."""
    routes: list[dict[str, t.Any]] = []

    for p in sorted(api_dir.rglob("*.py"), key=lambda x: str(x).lower()):
        if "__pycache__" in p.parts:
            continue
        if p.name in {"__init__.py"} or p.name.startswith("_"):
            continue

        tokens = _tokens_from_path(p, api_dir=api_dir)
        pattern = "/" + "/".join([("{" + v + "}") if k == "param" else v for k, v in tokens])
        pattern = pattern if pattern != "" else "/"

        routes.append(
            {
                "file": p,
                "tokens": tokens,
                "pattern": pattern,
                "param_count": sum(1 for k, _ in tokens if k == "param"),
                "static_count": sum(1 for k, _ in tokens if k == "static"),
            }
        )

    # Prefer more specific first: static beats dynamic, then longer/static beats shorter
    routes.sort(key=lambda r: (r["param_count"], -r["static_count"], r["pattern"]))
    return routes


def _dir_mtime(root: Path, *, suffixes: set[str] | None = None) -> int:
    """Return the newest mtime for files under root that match suffixes."""
    if not root.exists():
        return 0
    newest = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if suffixes is not None and path.suffix not in suffixes:
            continue
        try:
            newest = max(newest, path.stat().st_mtime_ns)
        except OSError:
            continue
    return newest


def _resolve_manifest_path(assets_dir: Path) -> Path | None:
    """Return the Vite manifest path if it exists."""
    manifest_path = assets_dir / "manifest.json"
    if manifest_path.exists():
        return manifest_path
    manifest_path = assets_dir / ".vite" / "manifest.json"
    if manifest_path.exists():
        return manifest_path
    return None


def _tokens_from_path(file_path: Path, *, api_dir: Path) -> list[tuple[str, str]]:
    """Convert a file path into route tokens (static/dynamic segments)."""
    rel = file_path.relative_to(api_dir)

    dir_parts = [] if str(rel.parent) == "." else list(rel.parent.parts)
    stem_parts = [s.strip() for s in rel.stem.split(".") if s.strip()]

    # index.py at root => /api
    if rel.name == "index.py" and not dir_parts:
        return []

    tokens: list[tuple[str, str]] = []
    for seg in dir_parts + stem_parts:
        if seg.startswith("[") and seg.endswith("]"):
            name = seg[1:-1].strip()
            if name and not name[0].isdigit():
                tokens.append(("param", name))
            else:
                tokens.append(("static", name))
        else:
            tokens.append(("static", seg))

    return tokens


def _build_pages_route_table(pages_dir: Path) -> tuple[list[dict[str, t.Any]], Path | None]:
    """Scan TSX pages and build a routing table plus optional 404 page."""
    routes: list[dict[str, t.Any]] = []
    not_found_page: Path | None = None

    if not pages_dir.exists():
        return routes, None

    for p in sorted(pages_dir.rglob("*.tsx"), key=lambda x: str(x).lower()):
        if "__pycache__" in p.parts:
            continue
        if p.name == "__init__.py":
            continue
        if p.name == "[404].tsx":
            not_found_page = p
            continue

        tokens = _tokens_from_pages_path(p, pages_dir=pages_dir)
        pattern = "/" + "/".join([("{" + v + "}") if k == "param" else v for k, v in tokens])
        pattern = pattern if pattern != "" else "/"

        routes.append(
            {
                "file": p,
                "tokens": tokens,
                "pattern": pattern,
                "param_count": sum(1 for k, _ in tokens if k == "param"),
                "static_count": sum(1 for k, _ in tokens if k == "static"),
            }
        )

    routes.sort(key=lambda r: (r["param_count"], -r["static_count"], r["pattern"]))
    return routes, not_found_page


def _tokens_from_pages_path(file_path: Path, *, pages_dir: Path) -> list[tuple[str, str]]:
    """Convert a page path into route tokens (static/dynamic segments)."""
    rel = file_path.relative_to(pages_dir)

    dir_parts = [] if str(rel.parent) == "." else list(rel.parent.parts)
    stem_parts = [s.strip() for s in rel.stem.split(".") if s.strip()]

    if rel.name == "index.tsx" and not dir_parts:
        return []

    tokens: list[tuple[str, str]] = []
    for seg in dir_parts + stem_parts:
        if seg.startswith("[") and seg.endswith("]"):
            name = seg[1:-1].strip()
            if name and not name[0].isdigit():
                tokens.append(("param", name))
            else:
                tokens.append(("static", name))
        else:
            tokens.append(("static", seg))

    return tokens


def _find_manifest_entry_by_src(manifest: dict[str, Any], src_suffix: str) -> dict[str, Any] | None:
    """Find a Vite manifest entry whose src ends with the given suffix."""
    for entry in manifest.values():
        if not isinstance(entry, dict):
            continue
        src = entry.get("src")
        if isinstance(src, str) and src.endswith(src_suffix):
            return entry
    return None


def _resolve_manifest_entry(
    manifest: dict[str, Any],
    key: str,
    rel: str,
) -> dict[str, Any] | None:
    """Resolve a manifest entry by key/rel fallback rules."""
    candidates = [
        f"__entries__/{key}",
        f"__entries__/{key}.tsx",
        key,
        f"{key}.tsx",
    ]

    for candidate in candidates:
        entry = manifest.get(candidate)
        if entry is not None and _entry_has_js_file(entry):
            return entry

    entry = _find_manifest_entry_by_src(manifest, f"__entries__/{key}.tsx")
    if entry is not None and _entry_has_js_file(entry):
        return entry

    entry = _find_manifest_entry_by_src(manifest, rel) or _find_manifest_entry_by_src(
        manifest, f"{key}.tsx"
    )
    if entry is not None and _entry_has_js_file(entry):
        return entry

    asset_entry = _find_asset_entry_by_prefix(Path("."), key)
    if asset_entry is not None:
        return asset_entry

    return None


def _entry_has_js_file(entry: dict[str, Any]) -> bool:
    """Return True if a manifest entry points to a JS file."""
    file_name = entry.get("file")
    return isinstance(file_name, str) and file_name.endswith(".js")


def _collect_js_assets(manifest: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    """Collect JS assets for a manifest entry and its imports."""
    assets: list[str] = []
    file_name = entry.get("file")
    if isinstance(file_name, str) and file_name.endswith(".js"):
        assets.append(file_name)
    for item in entry.get("imports", []) or []:
        if isinstance(item, str) and item.endswith(".js"):
            imported = manifest.get(item)
            if isinstance(imported, dict):
                imported_file = imported.get("file")
                if isinstance(imported_file, str) and imported_file.endswith(".js"):
                    assets.append(imported_file)
                else:
                    assets.append(item)
            else:
                assets.append(item)
    return assets


def _find_asset_entry_by_prefix(assets_dir: Path, prefix: str) -> dict[str, Any] | None:
    """Fallback lookup for a JS asset entry by filename prefix."""
    if not assets_dir.exists():
        return None

    candidates: list[Path] = []
    for item in assets_dir.iterdir():
        if item.is_file() and item.suffix == ".js":
            candidates.append(item)

    for item in sorted(candidates):
        if item.name.startswith(f"{prefix}-") or item.stem == prefix:
            return {"file": item.name}

    return None


def _match_route(routes: list[dict[str, t.Any]], segments: list[str]) -> dict[str, t.Any] | None:
    """Return the first route that matches the given URL segments."""
    for r in routes:
        tokens = r["tokens"]
        if len(tokens) != len(segments):
            continue

        params: dict[str, str] = {}
        ok = True
        for (kind, val), seg in zip(tokens, segments):
            if kind == "static":
                if seg != val:
                    ok = False
                    break
            else:
                params[val] = seg

        if ok:
            return {"file": r["file"], "params": params, "pattern": r["pattern"]}
    return None


def _load_module_from_file(file_path: Path, *, api_dir: Path) -> ModuleType:
    """Load a Python module from a file path with reload support."""
    backend_root = api_dir.parent  # /app/backend
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    rel = file_path.relative_to(api_dir).with_suffix("")
    safe = "__".join(rel.parts).replace(".", "__").replace("[", "var_").replace("]", "")
    module_name = f"backend.api.__auto__.{safe}"

    # Track file mtime to avoid re-exec'ing the same module on every request
    mtime = os.path.getmtime(file_path)

    cached = sys.modules.get(module_name)
    if cached is not None and getattr(cached, "__loaded_ok__", False):
        cached_mtime = getattr(cached, "__file_mtime__", None)

        # If unchanged, reuse the module and DO NOT exec again
        if cached_mtime == mtime:
            return cached

        # File changed (dev reload): toss the old module so we can re-import cleanly
        sys.modules.pop(module_name, None)

    # If we have a partial/bad module lying around, remove it
    sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {file_path}")

    mod = importlib.util.module_from_spec(spec)

    # Insert before exec to support circular imports
    sys.modules[module_name] = mod

    try:
        spec.loader.exec_module(mod)
        setattr(mod, "__loaded_ok__", True)
        setattr(mod, "__file_mtime__", mtime)
        return mod
    except Exception:
        # CRITICAL: don't leave a half-imported module in sys.modules
        sys.modules.pop(module_name, None)
        raise



def _serialize(obj: t.Any) -> bytes:
    """Serialize endpoint output to bytes, defaulting to JSON."""
    if obj is None:
        cherrypy.response.status = 204
        return b""

    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    if isinstance(obj, str):
        return obj.encode("utf-8")

    obj = _dataclass_to_plain(obj)

    cherrypy.response.headers["Content-Type"] = "application/json; charset=utf-8"
    return json.dumps(obj).encode("utf-8")


def _dataclass_to_plain(x: t.Any) -> t.Any:
    """Recursively convert dataclasses to plain dicts/lists."""
    if is_dataclass(x):
        return {k: _dataclass_to_plain(v) for k, v in asdict(x).items()}
    if isinstance(x, list):
        return [_dataclass_to_plain(v) for v in x]
    if isinstance(x, dict):
        return {k: _dataclass_to_plain(v) for k, v in x.items()}
    return x


def _call_with_binding(fn: t.Callable[..., t.Any], route_params: dict[str, str]) -> t.Any:
    """Bind request parameters/body to a callable and invoke it."""
    sig = inspect.signature(fn)

    merged: dict[str, t.Any] = dict(getattr(cherrypy.request, "params", {}) or {})
    merged.update(route_params)

    body = _read_json_body()
    if isinstance(body, dict):
        for k, v in body.items():
            merged.setdefault(k, v)

    func = getattr(fn, "__func__", fn)
    try:
        hints = t.get_type_hints(func, globalns=getattr(func, "__globals__", None), localns=None)
    except Exception:
        hints = {}

    kwargs: dict[str, t.Any] = {}
    nonself_params = [p for p in sig.parameters.values() if p.name != "self"]
    for name, p in sig.parameters.items():
        if name == "self":
            continue

        ann = hints.get(name, p.annotation)

        if name in merged:
            raw = merged[name]
        else:
            # convenience: single dataclass param can bind from root body
            if len(nonself_params) == 1 and _is_dataclass_type(ann) and isinstance(body, dict):
                raw = body
            elif p.default is not inspect._empty:
                raw = p.default
            else:
                raise cherrypy.HTTPError(400, f"Missing param: {name}")

        kwargs[name] = _coerce(raw, ann)

    return fn(**kwargs)


def _read_json_body() -> t.Any:
    """Parse and cache a JSON request body, returning dict or None."""
    if hasattr(cherrypy.request, "_cached_json"):
        return getattr(cherrypy.request, "_cached_json")

    ct = (cherrypy.request.headers.get("Content-Type") or "").lower()
    if "application/json" not in ct:
        setattr(cherrypy.request, "_cached_json", None)
        return None

    raw = cherrypy.request.body.read() or b"{}"
    try:
        val = json.loads(raw.decode("utf-8"))
    except Exception:
        raise cherrypy.HTTPError(400, "Invalid JSON")

    setattr(cherrypy.request, "_cached_json", val)
    return val


def _is_dataclass_type(ann: t.Any) -> bool:
    """Return True when a type annotation is a dataclass class."""
    try:
        return inspect.isclass(ann) and is_dataclass(ann)
    except Exception:
        return False


def _coerce(value: t.Any, ann: t.Any) -> t.Any:
    """Coerce basic types and dataclasses to match a signature annotation."""
    if ann in (None, inspect._empty):
        return value

    if _is_dataclass_type(ann):
        if isinstance(value, dict):
            return ann(**value)
        return value

    if ann is int:
        return int(value)
    if ann is float:
        return float(value)
    if ann is bool:
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "y"}
    if ann is str:
        return str(value)

    return value
