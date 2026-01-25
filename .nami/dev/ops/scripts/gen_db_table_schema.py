#!/usr/bin/env python3
from __future__ import annotations

"""
Generate Postgres CREATE TABLE IF NOT EXISTS SQL for dataclasses decorated with @db.table.

Usage:
  python3 ops/scripts/gen_pg_schema.py \
    "src/backend/api/*.py" \
    "src/backend/declarations/*.py" \
    --out src/backend/db/generated/schema.sql \
    --out-py src/backend/db/generated/schema_statements.py

Notes:
- Quoted globs are expanded by this script (so bash won't need to expand them).
- Passing a directory scans **/*.py under it.
- Table name defaults to snake_case(ClassName) unless overridden by @db.table(name="...").
- Schema defaults to "public" unless overridden by @db.table(schema="...").
- Column types are inferred from annotations; unknowns fall back to JSONB.
- Optional[T] / T | None makes column nullable.
- A field named "id" becomes PRIMARY KEY by default (unless metadata overrides).
"""

import argparse
import ast
import glob
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}


# ----------------- models -----------------

@dataclass(frozen=True)
class ColumnSpec:
    name: str
    pg_type: str
    nullable: bool
    is_pk: bool
    default_sql: str | None


@dataclass(frozen=True)
class TableSpec:
    schema: str
    name: str
    columns: list[ColumnSpec]
    source: str  # file:line


# ----------------- small utils -----------------

def snake(s: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(s):
        if ch.isupper() and i != 0 and (s[i - 1].islower() or (i + 1 < len(s) and s[i + 1].islower())):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def qident(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def sql_literal_from_constant(v: Any) -> str | None:
    # Only for simple constants (no evaluation of arbitrary expressions)
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return None


def _is_excluded(p: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in p.parts)


# ----------------- input expansion -----------------

def resolve_inputs(patterns: list[str]) -> list[Path]:
    """
    Accepts:
      - files
      - directories (expanded to **/*.py)
      - glob patterns (expanded with glob.glob(..., recursive=True))
    """
    if not patterns:
        patterns = ["src/**/*.py"]

    files: set[Path] = set()

    for pat in patterns:
        p = Path(pat)

        # directory -> **/*.py
        if p.exists() and p.is_dir():
            for f in p.rglob("*.py"):
                if not _is_excluded(f):
                    files.add(f.resolve())
            continue

        # glob pattern -> expand
        for hit in glob.glob(pat, recursive=True):
            f = Path(hit)
            if f.is_file() and f.suffix == ".py" and not _is_excluded(f):
                files.add(f.resolve())

    return sorted(files)


# ----------------- decorator detection -----------------

def _dec_base(dec: ast.expr) -> ast.expr:
    return dec.func if isinstance(dec, ast.Call) else dec


def is_dataclass_decorator(dec: ast.expr) -> bool:
    base = _dec_base(dec)
    # @dataclass or @dataclasses.dataclass
    if isinstance(base, ast.Name) and base.id == "dataclass":
        return True
    if isinstance(base, ast.Attribute) and base.attr == "dataclass":
        return True
    return False


def is_db_table_decorator(dec: ast.expr) -> bool:
    base = _dec_base(dec)
    # @db.table or @something.table (we only check tail attr)
    return isinstance(base, ast.Attribute) and base.attr == "table"


def parse_db_table_args(dec: ast.expr) -> tuple[str | None, str]:
    """
    Supports:
      @db.table
      @db.table(name="notes")
      @db.table(schema="app", name="notes")
    Defaults schema="public"
    """
    if not isinstance(dec, ast.Call):
        return None, "public"

    name: str | None = None
    schema: str = "public"

    for kw in dec.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            name = kw.value.value
        elif kw.arg == "schema" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            schema = kw.value.value

    return name, schema


# ----------------- annotation parsing -----------------

def unwrap_optional(ann: ast.AST) -> tuple[ast.AST, bool]:
    """
    Returns (inner_annotation, is_nullable)
    Handles:
      Optional[T]
      Union[T, None]
      T | None
    """
    # Optional[T] / Union[...]
    if isinstance(ann, ast.Subscript):
        # Optional[T]
        if isinstance(ann.value, ast.Name) and ann.value.id == "Optional":
            return ann.slice, True
        if isinstance(ann.value, ast.Attribute) and ann.value.attr == "Optional":
            return ann.slice, True

        # Union[T, None]
        if isinstance(ann.value, ast.Name) and ann.value.id == "Union":
            elts = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            if any(isinstance(e, ast.Constant) and e.value is None for e in elts):
                other = next(e for e in elts if not (isinstance(e, ast.Constant) and e.value is None))
                return other, True

    # PEP604: T | None
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        left, right = ann.left, ann.right
        if isinstance(left, ast.Constant) and left.value is None:
            return right, True
        if isinstance(right, ast.Constant) and right.value is None:
            return left, True

    return ann, False


def ann_to_pg_type(ann: ast.AST) -> str:
    # builtins
    if isinstance(ann, ast.Name):
        return {
            "str": "TEXT",
            "int": "BIGINT",
            "float": "DOUBLE PRECISION",
            "bool": "BOOLEAN",
            "bytes": "BYTEA",
            "Any": "JSONB",
        }.get(ann.id, "JSONB")

    # datetime/date/uuid/Decimal by tail attribute
    if isinstance(ann, ast.Attribute):
        tail = ann.attr
        if tail == "datetime":
            return "TIMESTAMPTZ"
        if tail == "date":
            return "DATE"
        if tail == "UUID":
            return "UUID"
        if tail == "Decimal":
            return "NUMERIC"
        return "JSONB"

    # list[T] -> T[] for simple types, else JSONB
    if isinstance(ann, ast.Subscript):
        if isinstance(ann.value, ast.Name) and ann.value.id in {"list", "List"}:
            inner = ann.slice
            inner, _nullable = unwrap_optional(inner)
            inner_pg = ann_to_pg_type(inner)
            if inner_pg in {"TEXT", "BIGINT", "DOUBLE PRECISION", "BOOLEAN", "UUID"}:
                return f"{inner_pg}[]"
            return "JSONB"

        # dict/set/tuple -> JSONB
        if isinstance(ann.value, ast.Name) and ann.value.id in {"dict", "Dict", "set", "Set", "tuple", "Tuple"}:
            return "JSONB"

        return "JSONB"

    return "JSONB"


# ----------------- field(metadata=...) parsing -----------------

def _parse_simple_dict(node: ast.AST) -> dict[str, Any] | None:
    """
    Parses dict literals with simple constant keys/values.
    Returns None if it’s not a simple dict.
    """
    if not isinstance(node, ast.Dict):
        return None

    out: dict[str, Any] = {}
    for k, v in zip(node.keys, node.values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            return None
        key = k.value
        if isinstance(v, ast.Constant):
            out[key] = v.value
        else:
            # non-constant in metadata -> ignore entire dict
            return None
    return out


def parse_field_metadata(value_expr: ast.AST | None) -> dict[str, Any]:
    """
    Supports:
      x: int = field(metadata={"pg_type": "UUID", "default_sql": "gen_random_uuid()"})
    """
    if value_expr is None:
        return {}

    if not isinstance(value_expr, ast.Call):
        return {}

    # field(...) or dataclasses.field(...)
    if isinstance(value_expr.func, ast.Name) and value_expr.func.id != "field":
        return {}
    if isinstance(value_expr.func, ast.Attribute) and value_expr.func.attr != "field":
        return {}
    if isinstance(value_expr.func, ast.Name) and value_expr.func.id != "field":
        return {}
    if isinstance(value_expr.func, ast.Attribute) and value_expr.func.attr != "field":
        return {}

    md: dict[str, Any] = {}
    for kw in value_expr.keywords:
        if kw.arg == "metadata":
            parsed = _parse_simple_dict(kw.value)
            if parsed:
                md.update(parsed)

    return md


# ----------------- extraction + SQL rendering -----------------

def extract_columns(cls: ast.ClassDef) -> list[ColumnSpec]:
    cols: list[ColumnSpec] = []
    saw_pk = False

    for node in cls.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name):
            continue

        col_name = node.target.id

        ann, nullable = unwrap_optional(node.annotation)
        inferred_pg_type = ann_to_pg_type(ann)

        md = parse_field_metadata(node.value)
        pg_type = str(md.get("pg_type") or inferred_pg_type)

        # primary key heuristic + override
        pk_flag = md.get("primary_key", None)
        is_pk = False
        if pk_flag is True:
            is_pk = True
        elif pk_flag is False:
            is_pk = False
        else:
            # default heuristic: first "id" field becomes PK
            if col_name == "id" and not saw_pk:
                is_pk = True

        if is_pk and not saw_pk:
            saw_pk = True
            nullable = False

        default_sql: str | None = None
        if isinstance(md.get("default_sql"), str):
            default_sql = md["default_sql"]

        cols.append(
            ColumnSpec(
                name=col_name,
                pg_type=pg_type,
                nullable=nullable,
                is_pk=is_pk,
                default_sql=default_sql,
            )
        )

    return cols


def make_create_sql(t: TableSpec) -> str:
    lines: list[str] = []

    for c in t.columns:
        parts = [qident(c.name), c.pg_type]

        if c.is_pk:
            if c.pg_type in {"BIGINT", "INTEGER"}:
                parts.append("GENERATED BY DEFAULT AS IDENTITY")
            parts.append("PRIMARY KEY")

        if not c.nullable:
            parts.append("NOT NULL")

        if c.default_sql:
            parts.append(f"DEFAULT {c.default_sql}")

        lines.append("  " + " ".join(parts))

    cols = ",\n".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {qident(t.schema)}.{qident(t.name)} (\n{cols}\n);"


def find_tables(py_file: Path, repo_root: Path) -> list[TableSpec]:
    try:
        src = py_file.read_text(encoding="utf-8")
        mod = ast.parse(src, filename=str(py_file))
    except Exception:
        return []

    tables: list[TableSpec] = []

    for node in mod.body:
        if not isinstance(node, ast.ClassDef):
            continue

        decs = node.decorator_list or []
        has_dc = any(is_dataclass_decorator(d) for d in decs)
        has_tbl = any(is_db_table_decorator(d) for d in decs)
        if not (has_dc and has_tbl):
            continue

        table_name: str | None = None
        schema: str = "public"

        for d in decs:
            if is_db_table_decorator(d):
                table_name, schema = parse_db_table_args(d)
                break

        name = table_name or snake(node.name)
        cols = extract_columns(node)
        if not cols:
            continue

        try:
            rel = py_file.relative_to(repo_root).as_posix()
        except Exception:
            rel = str(py_file)

        tables.append(
            TableSpec(
                schema=schema,
                name=name,
                columns=cols,
                source=f"{rel}:{getattr(node, 'lineno', '?')}",
            )
        )

    return tables


# ----------------- main -----------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate Postgres schema SQL for @db.table + @dataclass classes.",
    )
    ap.add_argument(
        "inputs",
        nargs="*",
        help='Files/dirs/globs to scan (e.g. "src/backend/api/*.py" "src/backend/declarations/*.py")',
    )
    ap.add_argument(
        "--out",
        required=True,
        help="Output .sql file path",
    )
    ap.add_argument(
        "--out-py",
        default="",
        help="Optional: output python file containing STATEMENTS=[...]",
    )
    args = ap.parse_args()

    repo_root = Path.cwd().resolve()
    py_files = resolve_inputs(args.inputs)

    if not py_files:
        print("No Python files matched the given inputs.", file=sys.stderr)
        return 2

    all_tables: list[TableSpec] = []
    for f in py_files:
        all_tables.extend(find_tables(f, repo_root))

    # deterministic output
    all_tables.sort(key=lambda t: (t.schema, t.name, t.source))

    out_sql = Path(args.out).resolve()
    out_sql.parent.mkdir(parents=True, exist_ok=True)

    sql_chunks: list[str] = []
    sql_chunks.append("-- AUTO-GENERATED FILE. DO NOT EDIT.")
    sql_chunks.append("-- Generated by ops/scripts/gen_pg_schema.py")
    sql_chunks.append("")

    for t in all_tables:
        sql_chunks.append(f"-- source: {t.source}")
        sql_chunks.append(make_create_sql(t))
        sql_chunks.append("")

    out_sql.write_text("\n".join(sql_chunks).rstrip() + "\n", encoding="utf-8")

    if args.out_py:
        out_py = Path(args.out_py).resolve()
        out_py.parent.mkdir(parents=True, exist_ok=True)
        stmts = [make_create_sql(t) for t in all_tables]
        out_py.write_text("STATEMENTS = " + repr(stmts) + "\n", encoding="utf-8")

    print(f"Scanned files: {len(py_files)}")
    print(f"Found tables:  {len(all_tables)}")
    print(f"Wrote SQL:     {out_sql}")
    if args.out_py:
        print(f"Wrote PY:      {Path(args.out_py).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
