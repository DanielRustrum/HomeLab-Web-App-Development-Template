from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import typing as t
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import ModuleType

import cherrypy


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
_ALREADY_MOUNTED = False


class Endpoint:
    """Base class for endpoint modules: class Endpoint(endpoints.Endpoint)."""

    def init(self) -> None: ...
    def auth(self) -> None: ...
    def cleanup(self) -> None: ...

    def _run(self, method: str, route_params: dict[str, str]) -> t.Any:
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


from __future__ import annotations
from typing import Any, Callable

def params(spec: dict[str, Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        return fn
    return deco










def mount_api(*, api_root: str = "/api", api_dir: str | Path | None = None) -> None:
    """
    Mount a dynamic router at /api that maps endpoint files in backend/api/**.

    Filename rules:
      notes.py            -> /api/notes
      notes.[id].py       -> /api/notes/<id>
      admin/users.py      -> /api/admin/users
      admin/users.[uid].py-> /api/admin/users/<uid>
      index.py            -> /api
    """
    global _ALREADY_MOUNTED
    if _ALREADY_MOUNTED:
        return

    backend_root = Path(__file__).resolve().parents[1]  # /app/backend

    if api_dir is None:
        api_dir_path = backend_root / "api"
    else:
        api_dir_path = Path(api_dir)
        if not api_dir_path.is_absolute():
            api_dir_path = backend_root / api_dir_path

    router = ApiRouter(api_dir=api_dir_path)
    cherrypy.tree.mount(router, "/" + api_root.strip("/"))

    _ALREADY_MOUNTED = True


class ApiRouter:
    """
    Mounted at /api. Uses default() to catch /api/* and dispatches to files in backend/api.
    """

    def __init__(self, *, api_dir: Path) -> None:
        self.api_dir = Path(api_dir).resolve()
        self._routes = _build_route_table(self.api_dir)
        self._endpoint_cache: dict[Path, type[Endpoint]] = {}

    @cherrypy.expose
    def index(self):
        # /api
        return _serialize({"ok": True})

    @cherrypy.expose
    def __routes(self):
        # /api/__routes  (debug)
        return _serialize(
            {
                "api_dir": str(self.api_dir),
                "routes": [r["pattern"] for r in self._routes],
            }
        )

    @cherrypy.expose
    def default(self, *vpath, **_params):
        # /api/<anything...>
        segments = [s for s in vpath if s]
        match = _match_route(self._routes, segments)
        if match is None:
            raise cherrypy.HTTPError(404, "No matching endpoint")

        endpoint_cls = self._load_endpoint_cls(match["file"])
        ep: Endpoint = endpoint_cls()

        method = (cherrypy.request.method or "GET").lower()
        if method not in _HTTP_METHODS:
            raise cherrypy.HTTPError(405)

        result = ep._run(method, match["params"])
        return _serialize(result)

    def _load_endpoint_cls(self, file_path: Path) -> type[Endpoint]:
        cached = self._endpoint_cache.get(file_path)
        if cached is not None:
            return cached


        mod = _load_module_from_file(file_path, api_dir=self.api_dir)
        endpoint_cls = getattr(mod, "Endpoint", None)
        if endpoint_cls is None or not inspect.isclass(endpoint_cls):
            raise cherrypy.HTTPError(500, f"{file_path.name} must export class Endpoint")

        self._endpoint_cache[file_path] = endpoint_cls
        return endpoint_cls


def _build_route_table(api_dir: Path) -> list[dict[str, t.Any]]:
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


def _tokens_from_path(file_path: Path, *, api_dir: Path) -> list[tuple[str, str]]:
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
            if not name or name[0].isdigit():
                raise ValueError(f"Invalid param segment {seg} in {file_path.name}")
            tokens.append(("param", name))
        else:
            tokens.append(("static", seg))

    return tokens


def _match_route(routes: list[dict[str, t.Any]], segments: list[str]) -> dict[str, t.Any] | None:
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
    backend_root = api_dir.parent  # /app/backend
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    rel = file_path.relative_to(api_dir).with_suffix("")
    safe = "__".join(rel.parts).replace(".", "__").replace("[", "var_").replace("]", "")
    module_name = f"backend.api.__auto__.{safe}"

    # If we have a cached module, only trust it if it fully loaded last time
    cached = sys.modules.get(module_name)
    if cached is not None and getattr(cached, "__loaded_ok__", False):
        return cached

    # Otherwise, throw away any partial/bad module and re-import
    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {file_path}")

    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod

    try:
        spec.loader.exec_module(mod)
        setattr(mod, "__loaded_ok__", True)
        return mod
    except Exception:
        # CRITICAL: don't leave a half-imported module in sys.modules
        sys.modules.pop(module_name, None)
        raise


def _serialize(obj: t.Any) -> bytes:
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
    if is_dataclass(x):
        return {k: _dataclass_to_plain(v) for k, v in asdict(x).items()}
    if isinstance(x, list):
        return [_dataclass_to_plain(v) for v in x]
    if isinstance(x, dict):
        return {k: _dataclass_to_plain(v) for k, v in x.items()}
    return x


def _call_with_binding(fn: t.Callable[..., t.Any], route_params: dict[str, str]) -> t.Any:
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
    try:
        return inspect.isclass(ann) and is_dataclass(ann)
    except Exception:
        return False


def _coerce(value: t.Any, ann: t.Any) -> t.Any:
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
