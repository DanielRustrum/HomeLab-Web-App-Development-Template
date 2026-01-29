"""Database helpers, schema mapping, and query utilities."""
# backend/core/db.py
from __future__ import annotations

import inspect
import re
import sys
import threading
import time
from dataclasses import asdict, is_dataclass, fields as dc_fields
from functools import wraps
from typing import (
    Any,
    Annotated,
    Callable,
    Generic,
    ParamSpec,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
    overload,
    Sequence,
    Union
)

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    Table as SATable,
    Text,
    bindparam,
    create_engine,
    insert,
    select,
    text,
    delete, 
    tuple_,
    exists as sa_exists, 
    func, 
    tuple_, 
    update as sa_update,
    or_
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import class_mapper, registry
from sqlalchemy.orm.exc import UnmappedClassError
from sqlalchemy.schema import CreateIndex, CreateTable

try:
    # Python 3.12+ (PEP 695 runtime object)
    from typing import TypeAliasType  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    TypeAliasType = None  # type: ignore[assignment]


T = TypeVar("T")
P = ParamSpec("P")
R = TypeVar("R")


# ======================================================================================
# Field markers: db.Key[T], db.Unique[T]
# (generic classes, not PEP695 type aliases => reliable at runtime)
# ======================================================================================

K = TypeVar("K")


class Key(Generic[K]):
    """Marker wrapper indicating a primary key field."""
    __db_marker__ = "key"


class Unique(Generic[K]):
    """Marker wrapper indicating a unique field."""
    __db_marker__ = "unique"


# optional lowercase aliases
key = Key
unique = Unique


def _unwrap_aliases(tp: Any) -> Any:
    """Resolve alias wrappers (TypeAliasType/NewType) to their base type."""
    # unwrap PEP 695 alias: `type NoteId = int`
    if TypeAliasType is not None and isinstance(tp, TypeAliasType):  # type: ignore[arg-type]
        return _unwrap_aliases(tp.__value__)  # type: ignore[attr-defined]
    # unwrap NewType("X", int)
    if hasattr(tp, "__supertype__"):
        return _unwrap_aliases(tp.__supertype__)
    return tp


def _analyze_type(tp: Any) -> tuple[Any, bool, bool, bool]:
    """
    returns: (base_type, nullable, is_pk, is_unique)

    Supports:
      - PEP 695 alias: `type NoteId = int`
      - NewType
      - Annotated[T, marker...]
      - Key[T] / Unique[T] generic wrappers
      - Optional[T] / T | None
    """
    is_pk = False
    is_unique = False

    def walk(t: Any) -> tuple[Any, bool]:
        """Walk nested annotations to identify flags and base type."""
        nonlocal is_pk, is_unique

        t = _unwrap_aliases(t)
        origin = get_origin(t)
        args = get_args(t)

        # Annotated[T, ...meta]
        if origin is Annotated:
            base, *meta = args
            for m in meta:
                tag = getattr(m, "__db_marker__", None)
                if tag == "key":
                    is_pk = True
                elif tag == "unique":
                    is_unique = True
            return walk(base)

        # Key[T] / Unique[T] wrapper (robust across duplicate imports)
        if origin is not None:
            tag = getattr(origin, "__db_marker__", None)
            if tag == "key":
                is_pk = True
                base = args[0] if args else Any
                return walk(base)
            if tag == "unique":
                is_unique = True
                base = args[0] if args else Any
                return walk(base)

        # Optional[T] / T | None
        if origin is not None and type(None) in args:
            inner = next(a for a in args if a is not type(None))
            base, _ = walk(inner)
            return base, True

        return t, False

    base, nullable = walk(tp)
    return base, nullable, is_pk, is_unique


# ======================================================================================
# Binding (must work across CherryPy worker threads)
# ======================================================================================

_BOUND_DB_LOCK = threading.Lock()
_BOUND_DB: "DB | None" = None


def bind_db(db: "DB") -> None:
    """Bind a DB for this process (thread-safe, visible to all request threads)."""
    global _BOUND_DB
    with _BOUND_DB_LOCK:
        _BOUND_DB = db


def get_db() -> "DB":
    """Return the bound DB or raise if no DB is configured."""
    db = _BOUND_DB
    if db is None:
        raise RuntimeError("DB not bound in this process. Call init_db(...) during startup.")
    return db


def _get_db_optional() -> "DB | None":
    """Return the bound DB if available, otherwise None."""
    return _BOUND_DB


# ======================================================================================
# Engine / init helpers
# ======================================================================================

class DB:
    """Engine holder. Bind once per process with init_db() or bind_db()."""

    def __init__(self, engine: Engine):
        """Create a DB wrapper around an existing SQLAlchemy engine."""
        self.engine = engine

    @classmethod
    def from_url(cls, url: str, *, echo: bool = False) -> "DB":
        """Create a DB wrapper around a SQLAlchemy engine."""
        engine = create_engine(
            url,
            echo=echo,
            future=True,
            pool_pre_ping=True,
        )
        return cls(engine)


def wait_for_db(engine: Engine, *, attempts: int = 60, sleep_s: float = 1.0) -> None:
    """Block until the database responds or raise after exhausting retries."""
    last_err: Exception | None = None
    for _ in range(attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as e:
            last_err = e
            time.sleep(sleep_s)
    assert last_err is not None
    raise last_err


def init_db(
    *,
    url: str,
    echo: bool = False,
    wait: bool = True,
    attempts: int = 60,
    sleep_s: float = 1.0,
    sync: bool = True,
) -> DB:
    """Initialize the engine, bind it globally, and optionally sync schema."""
    db = DB.from_url(url, echo=echo)
    bind_db(db)

    if wait:
        wait_for_db(db.engine, attempts=attempts, sleep_s=sleep_s)

    if sync:
        schema.sync_all(db.engine)

    return db


# ======================================================================================
# Schema / mapping
# ======================================================================================

_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")


def _snake(name: str) -> str:
    """Convert CamelCase names to snake_case."""
    name = _SNAKE_1.sub(r"\1_\2", name)
    return _SNAKE_2.sub(r"\1_\2", name).lower()


def _unwrap_to_base(tp: Any) -> Any:
    """Strip wrappers/aliases to reach the base Python type."""
    tp = _unwrap_aliases(tp)
    origin = get_origin(tp)
    args = get_args(tp)

    if origin is Annotated:
        base, *_meta = args
        return _unwrap_to_base(base)

    if origin is not None:
        tag = getattr(origin, "__db_marker__", None)
        if tag in ("key", "unique"):
            base = args[0] if args else Any
            return _unwrap_to_base(base)

    # Optional[T] / T|None
    if origin is not None and type(None) in args:
        inner = next(a for a in args if a is not type(None))
        return _unwrap_to_base(inner)

    return tp


def _sa_type_for(py_type: Any):
    """Map a Python type to a SQLAlchemy column type."""
    py_type = _unwrap_to_base(py_type)

    if py_type is int:
        return Integer()
    if py_type is str:
        return Text()
    if py_type is bool:
        return Boolean()
    if py_type is float:
        return Float()

    try:
        import datetime as _dt
        if py_type is _dt.datetime:
            return DateTime(timezone=True)
    except Exception:
        pass

    return Text()


class Schema:
    """Registry-backed schema helper for dataclass mapping."""
    def __init__(self):
        """Initialize the SQLAlchemy registry and metadata."""
        self._reg = registry()
        self.metadata: MetaData = self._reg.metadata

    def sync_all(self, engine: Engine) -> None:
        """Create all known tables and indexes if they do not exist."""
        with engine.begin() as conn:
            for table in self.metadata.sorted_tables:
                conn.execute(CreateTable(table, if_not_exists=True))
                for idx in table.indexes:
                    try:
                        conn.execute(CreateIndex(idx, if_not_exists=True))
                    except TypeError:
                        conn.execute(CreateIndex(idx))

    def sync_table(self, engine: Engine, table: SATable) -> None:
        """Create a single table and its indexes if they do not exist."""
        with engine.begin() as conn:
            conn.execute(CreateTable(table, if_not_exists=True))
            for idx in table.indexes:
                try:
                    conn.execute(CreateIndex(idx, if_not_exists=True))
                except TypeError:
                    conn.execute(CreateIndex(idx))

    @overload
    def table(self, cls: type[T], *, name: str | None = None) -> type[T]:
        """Type overload for direct decoration usage."""
        ...
    @overload
    def table(self, cls: None = None, *, name: str | None = None) -> Callable[[type[T]], type[T]]:
        """Type overload for decorator factory usage."""
        ...

    def table(self, cls=None, *, name: str | None = None):
        """Register a @dataclass model with the schema and SQLAlchemy mapping."""
        def deco(model: type[T]) -> type[T]:
            """Decorate a dataclass to create and map its SQL table."""
            if not is_dataclass(model):
                raise TypeError("@db.table must wrap a @dataclass class (apply @dataclass first)")

            table_name = name or _snake(model.__name__)

            # Evaluate annotations so wrappers resolve even under future annotations
            mod = sys.modules.get(model.__module__)
            globalns = vars(mod) if mod else {}
            hints = get_type_hints(model, globalns=globalns, localns=None, include_extras=True)

            analyzed: list[tuple[str, Any, bool, bool, bool]] = []
            for f in dc_fields(model):
                if f.init is False:
                    continue
                tp = hints.get(f.name, f.type)
                base_type, is_nullable, is_pk, is_unique = _analyze_type(tp)
                analyzed.append((f.name, base_type, is_nullable, is_pk, is_unique))

            cols: list[Column] = []
            for col_name, base_type, is_nullable, is_pk, is_unique in analyzed:
                sa_type = _sa_type_for(base_type)
                nullable = False if is_pk else is_nullable
                cols.append(
                    Column(
                        col_name,
                        sa_type,
                        primary_key=is_pk,
                        nullable=nullable,
                        unique=is_unique,
                    )
                )

            if not any(c.primary_key for c in cols):
                raise TypeError(
                    f"@db.table {model.__name__}: no primary key found. "
                    f"Mark one field as db.Key[...]."
                )

            # If an old/stale Table object exists in MetaData without PK, remove it so mapping works.
            existing = self.metadata.tables.get(table_name)
            if existing is not None and len(existing.primary_key.columns) == 0 and any(c.primary_key for c in cols):
                self.metadata.remove(existing)

            sa_table = SATable(table_name, self.metadata, *cols, extend_existing=True)

            # Map only if this class isn't already mapped
            try:
                class_mapper(model)
                already_mapped = True
            except UnmappedClassError:
                already_mapped = False

            if not already_mapped:
                self._reg.map_imperatively(model, sa_table)

            # If a DB is already bound in THIS process, create the table now.
            db = _get_db_optional()
            if db is not None:
                self.sync_table(db.engine, sa_table)

            return model

        return deco if cls is None else deco(cls)


schema = Schema()

@overload
def table(cls: type[T]) -> type[T]:
    """Type overload for direct decoration usage."""
    ...
@overload
def table(*, name: str | None = None) -> Callable[[type[T]], type[T]]:
    """Type overload for decorator factory usage."""
    ...
def table(cls=None, *, name: str | None = None):
    """Public decorator helper that forwards to schema.table()."""
    return schema.table(cls, name=name)


# ======================================================================================
# Query Builder + @query decorator
# ======================================================================================

_TLS = threading.local()


class QueryPlan:
    """Immutable plan describing a SQL operation and how to materialize results."""
    def __init__(self, *, kind: str, stmt: Any, mode: str, model: type | None = None, cast: Any = None):
        """Store the statement, execution mode, and optional cast info."""
        self.kind = kind
        self.stmt = stmt
        self.mode = mode
        self.model = model
        self.cast = cast


class QueryBuilder:
    """Builder for SQLAlchemy query plans with fluent helpers."""
    def __init__(self, model: type):
        """Initialize a builder for the given mapped model."""
        self.model = model
        tbl = getattr(model, "__table__", None)
        if tbl is None:
            raise RuntimeError(
                f"{model} is not mapped yet (missing __table__). "
                f"Did you forget to decorate it with @db.table?"
            )
        self._table = tbl

        self._conds: list[Any] = []          # track where clauses
        self._select_cols: list[Any] | None = None  # None means "all columns"
        self._stmt = select(tbl)


    def __getattr__(self, name: str):
        """Expose mapped columns as attributes for query building."""
        # notebook.book_title -> notebook.__table__.c.book_title
        try:
            return self._table.c[name]
        except KeyError as e:
            raise AttributeError(f"{self.model.__name__} has no column {name!r}") from e

                                 
    def where(self, *conds):
        """Add WHERE clauses to the current statement."""
        self._conds.extend(conds)
        self._stmt = self._stmt.where(*conds)
        return self
    
    def join(self, other: "QueryBuilder | type", *, when, isouter: bool = False):
        """Join another table or builder using the provided ON clause."""
        other_tbl = other._table if isinstance(other, QueryBuilder) else other.__table__
        self._stmt = self._stmt.join(other_tbl, onclause=when, isouter=isouter)
        return self

    def limit(self, n: int):
        """Limit the number of rows returned."""
        self._stmt = self._stmt.limit(n)
        return self

    def order_by(self, *cols):
        """Apply ORDER BY columns to the query."""
        self._stmt = self._stmt.order_by(*cols)
        return self

    def fetch_all(self) -> QueryPlan:
        """Return a query plan that fetches all rows."""
        plan = QueryPlan(kind="select", stmt=self._stmt, mode="all", model=self.model)
        _TLS.last_plan = plan
        return plan

    def fetch_amount(self, n: int) -> QueryPlan:
        """Return a plan limited to a fixed number of rows."""
        self.limit(n)
        return self.fetch_all()

    def fetch_first(self) -> QueryPlan:
        """Return a plan that fetches the first row or None."""
        plan = QueryPlan(kind="select", stmt=self._stmt, mode="first", model=self.model)
        _TLS.last_plan = plan
        return plan

    def fetch_one(self) -> QueryPlan:
        """Return a plan that expects exactly one row."""
        plan = QueryPlan(kind="select", stmt=self._stmt, mode="one", model=self.model)
        _TLS.last_plan = plan
        return plan
    
    def count(self) -> QueryPlan:
        """Return a plan that counts rows matching the current filter."""
        stmt = select(func.count()).select_from(self._table)
        if self._conds:
            stmt = stmt.where(*self._conds)
        plan = QueryPlan(kind="scalar", stmt=stmt, mode="one", cast=int)
        _TLS.last_plan = plan
        return plan
    
    def select(self, *cols: str | Any):
        """
        notebook.select("book_title")
        notebook.select(notebook.book_title)
        notebook.select("id", "title")
        """
        sel: list[Any] = []
        for c in cols:
            if isinstance(c, str):
                sel.append(self._table.c[c])
            else:
                sel.append(c)

        self._select_cols = sel
        self._stmt = select(*sel).select_from(self._table)
        if self._conds:
            self._stmt = self._stmt.where(*self._conds)
        return self

    def pattern(
        self,
        query: str,
        *,
        on: list[Any],
        case_insensitive: bool = True,
        mode: str = "contains",   # "contains" | "starts_with" | "ends_with" | "exact"
    ):
        """
        Build a simple text search over one or more columns.

        Example:
          notes.pattern("foo", on=[notes.title, notes.body]).fetch_all()

        Produces:
          WHERE (title ILIKE '%foo%' OR body ILIKE '%foo%')
        """

        if not on:
            raise ValueError("pattern(..., on=[...]) requires at least one column")

        # Convert mode -> LIKE pattern
        if mode == "contains":
            pat = f"%{query}%"
        elif mode == "starts_with":
            pat = f"{query}%"
        elif mode == "ends_with":
            pat = f"%{query}"
        elif mode == "exact":
            pat = f"{query}"
        else:
            raise ValueError(f"Unknown mode: {mode!r}")

        exprs = []
        for col in on:
            # allow passing column names as strings too
            if isinstance(col, str):
                col = self._table.c[col]

            if case_insensitive:
                exprs.append(col.ilike(pat))
            else:
                exprs.append(col.like(pat))

        return self.where(or_(*exprs))

    def exists(self) -> QueryPlan:
        """Return a plan that checks existence of matching rows."""
        inner = select(1).select_from(self._table)
        if self._conds:
            inner = inner.where(*self._conds)
        stmt = select(sa_exists(inner))
        plan = QueryPlan(kind="scalar", stmt=stmt, mode="one", cast=bool)
        _TLS.last_plan = plan
        return plan
    
    def update(self, allow_all: bool = False, **values: Any) -> QueryPlan:
        """Return an update plan, refusing unsafe global updates by default."""
        if not self._conds and not allow_all:
            raise RuntimeError(
                "Refusing to UPDATE without a WHERE clause. "
                "Call update(..., allow_all=True) if you really want to update everything."
            )
        stmt = sa_update(self._table).values(**values)
        if self._conds:
            stmt = stmt.where(*self._conds)
        plan = QueryPlan(kind="update", stmt=stmt, mode="rowcount", model=self.model)
        _TLS.last_plan = plan
        return plan

    def insert(self, obj: Any) -> QueryPlan:
        """
        Upsert (Postgres):
          - if obj has PK value(s) -> INSERT .. ON CONFLICT (pk) DO UPDATE
          - if obj.pk is None -> plain INSERT (DB must generate PK if you omit it)
        """
        data = asdict(obj) if is_dataclass(obj) else dict(obj)

        tbl = self.model.__table__
        pk_cols = [c.name for c in tbl.primary_key.columns]

        pk_missing = any((k not in data) or (data.get(k) is None) for k in pk_cols)
        if pk_missing:
            for k in pk_cols:
                if data.get(k) is None:
                    data.pop(k, None)
            stmt = insert(tbl).values(**data)
            plan = QueryPlan(kind="insert", stmt=stmt, mode="rowcount", model=self.model)
            _TLS.last_plan = plan
            return plan

        ins = pg_insert(tbl).values(**data)
        set_cols = {k: getattr(ins.excluded, k) for k in data.keys() if k not in pk_cols}

        if not set_cols:
            stmt = ins.on_conflict_do_nothing(index_elements=[tbl.c[k] for k in pk_cols])
        else:
            stmt = ins.on_conflict_do_update(
                index_elements=[tbl.c[k] for k in pk_cols],
                set_=set_cols,
            )

        plan = QueryPlan(kind="insert", stmt=stmt, mode="rowcount", model=self.model)
        _TLS.last_plan = plan
        return plan

    def delete(self, target: Any = None, *, allow_all: bool = False) -> "QueryPlan":
        """
        Supports both styles:

          # style A (recommended)
          notes.where(notes.title == title).delete()

          # style B (your sketch)
          notes.delete(notes.where(...).fetch_all())

        Behavior:
          - If target is None: DELETE using this builder's WHERE conds
          - If target is a QueryPlan(select): DELETE WHERE pk IN (subquery)
        """
        tbl = self._table
        pk_cols = list(tbl.primary_key.columns)

        if target is None:
            if not self._conds and not allow_all:
                raise RuntimeError(
                    "Refusing to DELETE without a WHERE clause. "
                    "Call .delete(allow_all=True) if you really want to delete everything."
                )
            stmt = delete(tbl)
            if self._conds:
                stmt = stmt.where(*self._conds)

        elif isinstance(target, QueryBuilder):
            if not target._conds and not allow_all:
                raise RuntimeError(
                    "Refusing to DELETE without a WHERE clause. "
                    "Call .delete(builder, allow_all=True) if intentional."
                )
            stmt = delete(tbl)
            if target._conds:
                stmt = stmt.where(*target._conds)

        elif isinstance(target, QueryPlan) and target.kind == "select":
            if not pk_cols:
                raise RuntimeError("Cannot delete from a select-plan: table has no primary key.")

            subq = target.stmt.subquery()

            if len(pk_cols) == 1:
                pk = pk_cols[0]
                stmt = delete(tbl).where(pk.in_(select(subq.c[pk.name])))
            else:
                stmt = delete(tbl).where(
                    tuple_(*pk_cols).in_(
                        select(*(subq.c[c.name] for c in pk_cols))
                    )
                )

        else:
            raise TypeError("delete() expects None, a QueryBuilder, or a QueryPlan(kind='select').")

        plan = QueryPlan(kind="delete", stmt=stmt, mode="rowcount", model=self.model)
        _TLS.last_plan = plan
        return plan


class Table:
    """
    Usage:
      with db.Table(Note) as notes: ...
      with db.Table([Notebook, Note]) as (notebook, notes): ...
    """

    def __init__(self, model_or_models: Union[type, Sequence[type]]):
        """Initialize a context manager for one or more models."""
        self._models = (
            list(model_or_models) if isinstance(model_or_models, (list, tuple)) else [model_or_models]
        )

    def __enter__(self):
        """Return query builders for the supplied models."""
        builders = [QueryBuilder(m) for m in self._models]
        return builders[0] if len(builders) == 1 else builders

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Do not suppress exceptions from the context block."""
        return False


def _row_to_kwargs(row: Any) -> dict[str, Any]:
    """Normalize SQLAlchemy row mappings into plain dicts."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(k, str):
            out[k] = v
        else:
            key = getattr(k, "key", None) or getattr(k, "name", None) or str(k)
            out[str(key)] = v
    return out


def _coerce_return(value: Any, return_type: Any) -> Any:
    """Coerce return values into dataclass wrappers when appropriate."""
    if return_type in (None, inspect._empty, type(None)):
        return value

    if isinstance(return_type, type) and is_dataclass(return_type):
        flds = dc_fields(return_type)
        names = {f.name for f in flds}

        if len(flds) == 1:
            return return_type(**{flds[0].name: value})

        if "notes" in names:
            if value is None:
                return return_type(notes=[])
            if isinstance(value, list):
                return return_type(notes=value)
            return return_type(notes=[value])

    return value


def query(fn: Callable[P, R]) -> Callable[P, R]:
    """Decorator that executes a query plan returned from a function."""
    return_type = fn.__annotations__.get("return", inspect._empty)

    @wraps(fn)
    def runner(*args: P.args, **kwargs: P.kwargs) -> R:
        """Execute the recorded query plan and coerce results."""
        _TLS.last_plan = None

        out = fn(*args, **kwargs)
        plan = out if isinstance(out, QueryPlan) else getattr(_TLS, "last_plan", None)
        if plan is None:
            raise RuntimeError(
                f"{fn.__name__} did not return a QueryPlan and did not record one "
                f"(did you forget fetch_all()/fetch_amount()/insert(...))?"
            )

        db = get_db()

        if plan.kind == "select":
            with db.engine.connect() as conn:
                res = conn.execute(plan.stmt)
                maps = res.mappings()

                if plan.mode == "all":
                    items = maps.all()
                elif plan.mode == "first":
                    one = maps.first()
                    items = [] if one is None else [one]
                elif plan.mode == "one":
                    items = [maps.one()]
                else:
                    raise ValueError(f"Unknown select mode: {plan.mode!r}")

                if plan.model is not None and is_dataclass(plan.model):
                    objs = [plan.model(**_row_to_kwargs(r)) for r in items]
                    value = objs if plan.mode == "all" else (objs[0] if objs else None)
                else:
                    dicts = [dict(r) for r in items]
                    value = dicts if plan.mode == "all" else (dicts[0] if dicts else None)

                return _coerce_return(value, return_type)

        if plan.kind == "insert":
            with db.engine.begin() as conn:
                res = conn.execute(plan.stmt)
                return res.rowcount
            
        if plan.kind == "scalar":
            with db.engine.connect() as conn:
                res = conn.execute(plan.stmt)
                val = res.scalar_one()
                if plan.cast is not None:
                    val = plan.cast(val)
                return val  # type: ignore[return-value]
            
        if plan.kind == "delete":
            with db.engine.begin() as conn:
                res = conn.execute(plan.stmt)
                # if you annotate -> None, return None; otherwise return rowcount
                if return_type in (None, inspect._empty, type(None)):
                    return None  # type: ignore[return-value]
                return res.rowcount  # type: ignore[return-value]


        raise ValueError(f"Unknown plan kind: {plan.kind!r}")

    return runner


__all__ = [
    "DB",
    "bind_db",
    "get_db",
    "init_db",
    "schema",
    "table",
    "Table",
    "query",
    "Key",
    "Unique",
    "key",
    "unique",
    "bindparam",
]
