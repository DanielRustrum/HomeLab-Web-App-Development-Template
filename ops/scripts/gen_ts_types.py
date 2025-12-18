# generate_ts.py
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

PRIMITIVE_MAP = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "None": "null",
    "Any": "any",
    "object": "unknown",
}

TYPING_ALIASES = {
    "List": "list",
    "Sequence": "list",
    "Iterable": "list",
    "Set": "set",
    "Dict": "dict",
    "Mapping": "dict",
    "Optional": "optional",
    "Union": "union",
    "Tuple": "tuple",
}


def _is_dataclass_decorator(dec: ast.expr) -> bool:
    # @dataclass
    if isinstance(dec, ast.Name) and dec.id == "dataclass":
        return True
    # @dataclasses.dataclass
    if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
        return True
    # @dataclass(...)
    if isinstance(dec, ast.Call):
        return _is_dataclass_decorator(dec.func)
    return False


def _collect_dataclasses(module: ast.Module) -> Dict[str, ast.ClassDef]:
    out: Dict[str, ast.ClassDef] = {}
    for node in module.body:
        if isinstance(node, ast.ClassDef):
            if any(_is_dataclass_decorator(d) for d in node.decorator_list):
                out[node.name] = node
    return out


def _collect_dataclass_fields(cls: ast.ClassDef) -> List[Tuple[str, ast.expr]]:
    fields: List[Tuple[str, ast.expr]] = []
    for stmt in cls.body:
        # name: Type = ...
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if stmt.annotation is not None:
                fields.append((stmt.target.id, stmt.annotation))
    return fields


def _name_of(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        # typing.List, dataclasses.dataclass, etc. Return final attr
        return node.attr
    return None



def _ts_type(
    ann: ast.expr,
    known_dataclasses: Set[str],
    referenced_dataclasses: Set[str],
    *,
    aliases: Optional[Dict[str, ast.expr]] = None,
    referenced_aliases: Optional[Set[str]] = None,
    preserve_aliases: bool = True,
    _resolving: Optional[Set[str]] = None,
) -> str:
    aliases = aliases or {}
    referenced_aliases = referenced_aliases if referenced_aliases is not None else set()
    _resolving = _resolving or set()

    # PEP604 unions: A | B
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        left = _ts_type(
            ann.left, known_dataclasses, referenced_dataclasses,
            aliases=aliases, referenced_aliases=referenced_aliases,
            preserve_aliases=preserve_aliases, _resolving=_resolving,
        )
        right = _ts_type(
            ann.right, known_dataclasses, referenced_dataclasses,
            aliases=aliases, referenced_aliases=referenced_aliases,
            preserve_aliases=preserve_aliases, _resolving=_resolving,
        )
        return f"{left} | {right}"

    # Simple names: User, str, int, NoteId, etc.
    if isinstance(ann, ast.Name):
        # Type alias: NoteId -> int (or other)
        if ann.id in aliases:
            if preserve_aliases:
                referenced_aliases.add(ann.id)
                return ann.id

            # resolve alias to its underlying TS type
            if ann.id in _resolving:
                return "unknown"  # break recursive aliases
            _resolving.add(ann.id)
            ts = _ts_type(
                aliases[ann.id], known_dataclasses, referenced_dataclasses,
                aliases=aliases, referenced_aliases=referenced_aliases,
                preserve_aliases=False, _resolving=_resolving,
            )
            _resolving.remove(ann.id)
            return ts

        # Dataclass name
        if ann.id in known_dataclasses:
            referenced_dataclasses.add(ann.id)
            return ann.id

        # Primitive
        return PRIMITIVE_MAP.get(ann.id, ann.id)  # fall back to same name

    # None literal in annotations (rare)
    if isinstance(ann, ast.Constant) and ann.value is None:
        return "null"

    # Subscript: list[T], Optional[T], Dict[K,V], Union[...], etc.
    if isinstance(ann, ast.Subscript):
        base = _name_of(ann.value) or "unknown"
        base = TYPING_ALIASES.get(base, base)

        # slice can be a Tuple (Dict[K,V]) or a single expr (List[T])
        args: List[ast.expr]
        if isinstance(ann.slice, ast.Tuple):
            args = list(ann.slice.elts)
        else:
            args = [ann.slice]

        if base in ("list", "set", "Sequence", "Iterable"):
            inner = _ts_type(
                args[0], known_dataclasses, referenced_dataclasses,
                aliases=aliases, referenced_aliases=referenced_aliases,
                preserve_aliases=preserve_aliases, _resolving=_resolving,
            ) if args else "unknown"
            return f"{inner}[]"

        if base == "dict":
            k = _ts_type(
                args[0], known_dataclasses, referenced_dataclasses,
                aliases=aliases, referenced_aliases=referenced_aliases,
                preserve_aliases=preserve_aliases, _resolving=_resolving,
            ) if len(args) > 0 else "string"
            v = _ts_type(
                args[1], known_dataclasses, referenced_dataclasses,
                aliases=aliases, referenced_aliases=referenced_aliases,
                preserve_aliases=preserve_aliases, _resolving=_resolving,
            ) if len(args) > 1 else "unknown"

            # TS Record keys should be string/number/symbol; coerce uncommon keys
            if k not in ("string", "number"):
                k = "string"
            return f"Record<{k}, {v}>"

        if base == "tuple":
            inners = ", ".join(
                _ts_type(
                    a, known_dataclasses, referenced_dataclasses,
                    aliases=aliases, referenced_aliases=referenced_aliases,
                    preserve_aliases=preserve_aliases, _resolving=_resolving,
                )
                for a in args
            )
            return f"[{inners}]"

        if base == "optional":
            inner = _ts_type(
                args[0], known_dataclasses, referenced_dataclasses,
                aliases=aliases, referenced_aliases=referenced_aliases,
                preserve_aliases=preserve_aliases, _resolving=_resolving,
            ) if args else "unknown"
            return f"{inner} | null"

        if base == "union":
            inners = " | ".join(
                _ts_type(
                    a, known_dataclasses, referenced_dataclasses,
                    aliases=aliases, referenced_aliases=referenced_aliases,
                    preserve_aliases=preserve_aliases, _resolving=_resolving,
                )
                for a in args
            )
            return inners or "unknown"

        # Unknown generic -> just emit base<...>
        inners = ", ".join(
            _ts_type(
                a, known_dataclasses, referenced_dataclasses,
                aliases=aliases, referenced_aliases=referenced_aliases,
                preserve_aliases=preserve_aliases, _resolving=_resolving,
            )
            for a in args
        )
        return f"{base}<{inners}>"

    # Fallback for anything else
    try:
        return PRIMITIVE_MAP.get(ast.unparse(ann), "unknown")
    except Exception:
        return "unknown"


def _find_method_return_annotation(module: ast.Module, class_name: str, method_name: str) -> Optional[ast.expr]:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == method_name:
                    return stmt.returns
    return None


def generate_ts_for_index(py_path: str, route_class: str = "Route", method: str = "index") -> str:
    src = Path(py_path).read_text(encoding="utf-8")
    module = ast.parse(src, filename=py_path)

    dataclasses = _collect_dataclasses(module)
    known_names = set(dataclasses.keys())

    ret_ann = _find_method_return_annotation(module, route_class, method)
    if ret_ann is None:
        raise RuntimeError(f"Could not find return annotation for {route_class}.{method}()")

    referenced: Set[str] = set()
    ts_return = _ts_type(ret_ann, known_names, referenced)

    # Build interfaces for any referenced dataclasses (including nested refs)
    emitted: Set[str] = set()
    lines: List[str] = []

    def emit_dataclass(name: str):
        if name in emitted:
            return
        cls = dataclasses.get(name)
        if cls is None:
            return
        emitted.add(name)

        fields = _collect_dataclass_fields(cls)
        # First, discover nested dataclass references in fields so we can emit those too
        local_refs: Set[str] = set()
        for _, ann in fields:
            _ts_type(ann, known_names, local_refs)

        for dep in sorted(local_refs):
            emit_dataclass(dep)

        lines.append(f"export interface {name} {{")
        for field_name, ann in fields:
            ts_t = _ts_type(ann, known_names, referenced)
            lines.append(f"  {field_name}: {ts_t};")
        lines.append("}")
        lines.append("")

    for dc in sorted(referenced):
        emit_dataclass(dc)

    return "\n".join(lines)

import argparse
from pathlib import Path
from typing import Iterable

def _iter_py_files(inputs: Iterable[str]) -> list[Path]:
    files: list[Path] = []

    for raw in inputs:
        p = Path(raw)

        # If user passed a directory, scan it recursively
        if p.exists() and p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
            continue

        # If user passed an existing file
        if p.exists() and p.is_file():
            if p.suffix == ".py":
                files.append(p)
            continue

        # Otherwise treat as a glob (relative to cwd)
        files.extend(sorted(Path(".").glob(raw)))

    # Dedup while preserving order
    seen = set()
    out: list[Path] = []
    for f in files:
        rf = f.resolve()
        if rf not in seen:
            seen.add(rf)
            out.append(f)
    return out


def generate_ts_for_files(
    py_files: list[Path],
    route_class: str = "Route",
    allowed_methods: set[str] | None = None,   # ✅ allowlist (None = all)
    limit: int | None = None,          # ✅ optional max count
) -> str:
    PARAM_METHODS = {"post", "put", "patch"}  # tweak if you want
    param_interfaces: dict[str, tuple[str, list[tuple[str, ast.expr | None, bool, ast.expr | None]]]] = {}


    parsed: list[tuple[Path, ast.Module]] = []
    for f in py_files:
        src = f.read_text(encoding="utf-8")
        try:
            module = ast.parse(src, filename=str(f))
        except SyntaxError as e:
            bad_line = src.splitlines()[e.lineno - 1] if e.lineno else ""
            raise RuntimeError(f"{f}:{e.lineno}:{e.offset} {e.msg}\n{bad_line}") from e
        parsed.append((f, module))

    # Global dataclass registry (dedup + collision check)
    dataclasses: dict[str, ast.ClassDef] = {}
    dataclass_sources: dict[str, Path] = {}

    # Global type-alias registry (type NoteId = int)
    aliases: dict[str, ast.expr] = {}
    alias_sources: dict[str, Path] = {}

    for f, module in parsed:
        # dataclasses
        local_dcs = _collect_dataclasses(module)
        for name, cls in local_dcs.items():
            if name in dataclasses:
                prev = dataclass_sources[name]
                raise RuntimeError(f"Dataclass name collision: {name} defined in both {prev} and {f}.")
            if name in aliases:
                prev = alias_sources[name]
                raise RuntimeError(f"Name collision: {name} is a type alias in {prev} and a dataclass in {f}.")
            dataclasses[name] = cls
            dataclass_sources[name] = f

        # type aliases
        local_aliases = _collect_type_aliases(module)
        for name, expr in local_aliases.items():
            if name in aliases:
                prev = alias_sources[name]
                raise RuntimeError(f"Type alias collision: {name} defined in both {prev} and {f}.")
            if name in dataclasses:
                prev = dataclass_sources[name]
                raise RuntimeError(f"Name collision: {name} is a dataclass in {prev} and a type alias in {f}.")
            aliases[name] = expr
            alias_sources[name] = f

    known_names = set(dataclasses.keys())

    referenced: set[str] = set()                 # dataclasses referenced by endpoints
    referenced_aliases: set[str] = set()         # aliases referenced by endpoints/fields

    for f, module in parsed:
        if f.name == "__init__.py":
            continue

        stem = f.stem
        methods = _collect_route_methods(module, route_class=route_class)
        if not methods:
            continue

        endpoints_map: dict[str, str] = {}  # replace endpoints list

        items = sorted(methods.items(), key=lambda kv: kv[0])  # stable order per file
        if limit is not None:
            items = items[:limit]

        for method_name, fn in items:
            if allowed_methods is not None and method_name not in allowed_methods:
                continue

            key = stem if method_name == "index" else f"{stem}.{method_name}"

            # Params → interface (post/put/patch)
            if method_name in PARAM_METHODS:
                params = _collect_method_params(fn)
                if params:
                    iface = f"{_to_pascal(stem)}{_to_pascal(method_name)}Body"
                    param_interfaces[key] = (iface, params)

                    # discover dataclasses/aliases used by params
                    for _, ann, _, _ in params:
                        if ann is not None:
                            _ts_type(
                                ann,
                                known_names,
                                referenced,
                                aliases=aliases,
                                referenced_aliases=referenced_aliases,
                            )

                    # ✅ THIS is the change you want:
                    endpoints_map[key] = iface
                    continue  # don’t also use return type

            # Return type → Endpoints map (fallback)
            if fn.returns is not None:
                ts_ret = _ts_type(
                    fn.returns,
                    known_names,
                    referenced,
                    aliases=aliases,
                    referenced_aliases=referenced_aliases,
                )
                if ts_ret == "null":
                    ts_ret = "void"
                endpoints_map[key] = ts_ret
            else:
                endpoints_map[key] = "unknown"

    # Emit interfaces (deps-first), deduped
    emitted: set[str] = set()
    lines: list[str] = []

    def emit_dataclass(name: str):
        if name in emitted:
            return
        cls = dataclasses.get(name)
        if cls is None:
            return
        emitted.add(name)

        fields = _collect_dataclass_fields(cls)

        # emit dataclass deps first
        local_refs: set[str] = set()
        for _, ann in fields:
            _ts_type(
                ann,
                known_names,
                local_refs,
                aliases=aliases,
                referenced_aliases=referenced_aliases,
            )
        for dep in sorted(local_refs):
            emit_dataclass(dep)

        lines.append(f"export interface {name} {{")
        for field_name, ann in fields:
            ts_t = _ts_type(
                ann,
                known_names,
                referenced,
                aliases=aliases,
                referenced_aliases=referenced_aliases,
            )
            lines.append(f"  {field_name}: {ts_t};")
        lines.append("}")
        lines.append("")

    for dc in sorted(referenced):
        emit_dataclass(dc)

    # Emit TS type-aliases that were actually referenced
    if referenced_aliases:
        for name in sorted(referenced_aliases):
            ts_def = _ts_type(
                aliases[name],
                known_names,
                referenced,
                aliases=aliases,
                referenced_aliases=referenced_aliases,
                preserve_aliases=False,   # resolve underlying type for the alias definition
            )
            lines.append(f"export type {name} = {ts_def};")
        lines.append("")

    # Emit param interfaces
    if param_interfaces:
        for key, (iface, params) in sorted(param_interfaces.items(), key=lambda x: x[0]):
            lines.append(f"export interface {iface} {{")
            for name, ann, has_default, default_expr in params:
                ts_t = _ts_type(
                    ann, known_names, referenced,
                    aliases=aliases, referenced_aliases=referenced_aliases,
                ) if ann is not None else "unknown"

                optional = "?" if has_default else ""
                # If default is None, allow null too (optional but handy)
                if has_default and isinstance(default_expr, ast.Constant) and default_expr.value is None and "null" not in ts_t:
                    ts_t = f"{ts_t} | null"

                lines.append(f"  {name}{optional}: {ts_t};")
            lines.append("}")
            lines.append("")

        lines.append("export type EndpointParams = {")
        for key, (iface, _) in sorted(param_interfaces.items(), key=lambda x: x[0]):
            lines.append(f'  "{key}": {iface};')
        lines.append("}")
        lines.append("")


    if endpoints_map:
        lines.append("export type Endpoints = {")
        for key, ts_t in sorted(endpoints_map.items(), key=lambda x: x[0]):
            lines.append(f'  "{key}": {ts_t};')
        lines.append("}")
        lines.append("")


    return "\n".join(lines).rstrip() + "\n"

def _collect_route_methods(module: ast.Module, route_class: str = "Route") -> dict[str, ast.expr]:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == route_class:
            out: dict[str, ast.FunctionDef] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef):
                    if stmt.name.startswith("_"):
                        continue
                    out[stmt.name] = stmt
            return out
    return {}

def _collect_type_aliases(module: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}

    for node in module.body:
        # Python 3.12+:  type NoteId = int
        TypeAlias = getattr(ast, "TypeAlias", None)
        if TypeAlias is not None and isinstance(node, TypeAlias):
            name_node = getattr(node, "name", None)
            if isinstance(name_node, ast.Name):
                out[name_node.id] = node.value
            elif isinstance(name_node, str):
                out[name_node] = node.value
            continue

        # Also support: NoteId: TypeAlias = int
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            ann = _name_of(node.annotation)
            if ann == "TypeAlias":
                out[node.target.id] = node.value

    return out

def _to_pascal(s: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in s.replace("-", "_").split("_") if part)

def _collect_method_params(fn: ast.FunctionDef) -> list[tuple[str, ast.expr | None, bool, ast.expr | None]]:
    """
    Returns list of (param_name, annotation_or_None, has_default, default_expr_or_None)
    for all params after self/cls.
    """
    out: list[tuple[str, ast.expr | None, bool, ast.expr | None]] = []

    pos_and_args = list(fn.args.posonlyargs) + list(fn.args.args)

    # defaults apply to the last N positional params
    defaults = list(fn.args.defaults)
    default_offset = len(pos_and_args) - len(defaults)

    for i, a in enumerate(pos_and_args):
        # skip self/cls (only if it's the first arg)
        if i == 0 and a.arg in ("self", "cls"):
            continue

        has_default = i >= default_offset and len(defaults) > 0
        default_expr = defaults[i - default_offset] if has_default else None
        out.append((a.arg, a.annotation, has_default, default_expr))

    # kw-only args
    for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        has_default = d is not None
        out.append((a.arg, a.annotation, has_default, d))

    # (optional) ignore *args/**kwargs for now (can be added later)

    return out



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="Python files, globs, or directories")
    parser.add_argument("--class", dest="route_class", default="Endpoint")

    # ✅ allowlist + limit
    parser.add_argument(
        "--allowed-methods",
        dest="allowed_methods",
        default=None,
        help="Comma-separated allowlist. Example: --allowed-methods get,post,init,cleanup (default: all)",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="Max number of methods per file (after sorting by name).",
    )

    parser.add_argument("--out", dest="out", default=None, help="Write to file instead of stdout")
    args = parser.parse_args()

    def _parse_allowed_methods(raw: str | None) -> set[str] | None:
        if not raw:
            return None
        s = {p.strip() for p in raw.split(",") if p.strip()}
        return s or None

    allowed = _parse_allowed_methods(args.allowed_methods)

    py_files = _iter_py_files(args.inputs)
    if not py_files:
        raise SystemExit("No .py files found from inputs.")

    ts = generate_ts_for_files(
        py_files,
        route_class=args.route_class,
        allowed_methods=allowed,
        limit=args.limit,
    )

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(ts, encoding="utf-8")
    else:
        print(ts, end="")
