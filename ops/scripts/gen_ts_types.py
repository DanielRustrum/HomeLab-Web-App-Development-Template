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
) -> str:
    # PEP604 unions: A | B
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        left = _ts_type(ann.left, known_dataclasses, referenced_dataclasses)
        right = _ts_type(ann.right, known_dataclasses, referenced_dataclasses)
        # make it TS union
        return f"{left} | {right}"

    # Simple names: User, str, int, etc.
    if isinstance(ann, ast.Name):
        if ann.id in known_dataclasses:
            referenced_dataclasses.add(ann.id)
            return ann.id
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
            inner = _ts_type(args[0], known_dataclasses, referenced_dataclasses) if args else "unknown"
            return f"{inner}[]"

        if base == "dict":
            k = _ts_type(args[0], known_dataclasses, referenced_dataclasses) if len(args) > 0 else "string"
            v = _ts_type(args[1], known_dataclasses, referenced_dataclasses) if len(args) > 1 else "unknown"
            # TS index signatures want string/number/symbol; we’ll coerce common cases
            if k not in ("string", "number"):
                k = "string"
            return f"Record<{k}, {v}>"

        if base == "tuple":
            inners = ", ".join(_ts_type(a, known_dataclasses, referenced_dataclasses) for a in args)
            return f"[{inners}]"

        if base == "optional":
            inner = _ts_type(args[0], known_dataclasses, referenced_dataclasses) if args else "unknown"
            return f"{inner} | null"

        if base == "union":
            inners = " | ".join(_ts_type(a, known_dataclasses, referenced_dataclasses) for a in args)
            return inners or "unknown"

        # Unknown generic -> just emit base<...>
        inners = ", ".join(_ts_type(a, known_dataclasses, referenced_dataclasses) for a in args)
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


def generate_ts_for_files(py_files: list[Path], route_class: str = "Route", method: str | None = None) -> str:
    parsed: list[tuple[Path, ast.Module]] = []
    for f in py_files:
        src = f.read_text(encoding="utf-8")
        module = ast.parse(src, filename=str(f))
        parsed.append((f, module))

    # Global dataclass registry (dedup + collision check)
    dataclasses: dict[str, ast.ClassDef] = {}
    dataclass_sources: dict[str, Path] = {}
    for f, module in parsed:
        local = _collect_dataclasses(module)
        for name, cls in local.items():
            if name in dataclasses:
                prev = dataclass_sources[name]
                raise RuntimeError(
                    f"Dataclass name collision: {name} defined in both {prev} and {f}."
                )
            dataclasses[name] = cls
            dataclass_sources[name] = f

    known_names = set(dataclasses.keys())

    referenced: set[str] = set()
    endpoints: list[tuple[str, str]] = []  # (key, ts_type)

    for f, module in parsed:
        if f.name == "__init__.py":
            continue

        stem = f.stem
        methods = _collect_route_method_returns(module, route_class=route_class)
        if not methods:
            continue

        for method_name, ret_ann in methods.items():
            if method is not None and method_name != method:
                continue

            ts_ret = _ts_type(ret_ann, known_names, referenced)
            key = stem if method_name == "index" else f"{stem}.{method_name}"
            endpoints.append((key, ts_ret))


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

        # emit deps first
        local_refs: set[str] = set()
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

    # Emit Endpoints map
    if endpoints:
        lines.append("export type Endpoints = {")
        for key, ts_t in sorted(endpoints, key=lambda x: x[0]):
            lines.append(f'  "{key}": {ts_t};')
        lines.append("}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

def _collect_route_method_returns(module: ast.Module, route_class: str = "Route") -> dict[str, ast.expr]:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == route_class:
            out: dict[str, ast.expr] = {}
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef):
                    if stmt.name.startswith("_"):
                        continue
                    if stmt.returns is None:
                        continue
                    out[stmt.name] = stmt.returns
            return out
    return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="Python files, globs, or directories")
    parser.add_argument("--class", dest="route_class", default="Route")
    parser.add_argument("--method", dest="method", default="index")
    parser.add_argument("--out", dest="out", default=None, help="Write to file instead of stdout")
    args = parser.parse_args()

    py_files = _iter_py_files(args.inputs)
    if not py_files:
        raise SystemExit("No .py files found from inputs.")

    ts = generate_ts_for_files(py_files, route_class=args.route_class, method=args.method)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(ts, encoding="utf-8")
    else:
        print(ts, end="")
