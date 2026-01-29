"""Generate TypeScript types from Python endpoint modules."""
# generate_ts.py
from __future__ import annotations

import argparse, ast, os, re

import glob as glob_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional


# ============================================================
# Configuration
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TYPE_MAP_PATH = ROOT_DIR / "src" / "type_mappings.yaml"


def load_type_mapping(path: Path) -> tuple[dict[str, str], dict[str, tuple[list[str], str]]]:
    """Load primitive and generic type mappings from a YAML-like file."""
    if not path.exists():
        return {}, {}

    primitive_mapping: dict[str, str] = {}
    generic_mapping: dict[str, tuple[list[str], str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if "<" in key and key.endswith(">"):
            base_name, params_part = key.split("<", 1)
            params = [param.strip() for param in params_part[:-1].split(",") if param.strip()]
            if not params:
                continue
            generic_mapping[base_name.strip()] = (params, value)
            continue

        primitive_mapping[key] = value
    return primitive_mapping, generic_mapping


@dataclass(frozen=True)
class TypeScriptGeneratorConfig:
    """Configuration for translating Python typing into TypeScript."""
    route_class_name: str = "Endpoint"
    type_suffix: str = "Object"

    # If set, treat index() as this method name when building endpoint keys (example: "get")
    index_method_alias: str | None = None

    # Methods that accept a body (signature params become EndpointParams entries)
    body_methods: frozenset[str] = frozenset({"post", "put", "patch"})

    # Methods treated as HTTP endpoint handlers for collection.
    http_methods: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
    include_never_for_non_body: bool = True

    # Optional emitted maps
    emit_query_params: bool = True
    emit_path_params: bool = True

    # Decorator names (DecoratorInstance.decorator_name)
    query_params_decorator_name: str = "params"

    primitive_type_map: dict[str, str] = field(
        default_factory=lambda: {
            "str": "string",
            "int": "number",
            "float": "number",
            "bool": "boolean",
            "None": "null",
            "Any": "any",
            "object": "unknown",
            "UUID": "string",
        }
    )
    generic_type_map: dict[str, tuple[list[str], str]] = field(default_factory=dict)

    typing_container_aliases: dict[str, str] = field(
        default_factory=lambda: {
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
    )
    passthrough_generic_modules: frozenset[str] = frozenset({"db"})


# ============================================================
# Naming + endpoint-key helpers
# ============================================================

DYNAMIC_SEGMENT_REGEX = re.compile(r"\[([^\]]+)\]")


def to_pascal_case(text: str) -> str:
    """Convert a path-like or dotted string into PascalCase."""
    normalized = re.sub(r"\[([^\]]+)\]", r"_\1_", text)
    normalized = normalized.replace(".", "_")
    normalized = re.sub(r"[^0-9a-zA-Z_]+", "_", normalized)
    parts = [part for part in normalized.split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def to_typescript_type_symbol(config: TypeScriptGeneratorConfig, python_name: str) -> str:
    """Append the configured suffix to a Python symbol name."""
    return f"{python_name}{config.type_suffix}"


def name_of_ast_expression(expression_node: ast.expr) -> Optional[str]:
    """Return the identifier name for AST Name/Attribute nodes."""
    if isinstance(expression_node, ast.Name):
        return expression_node.id
    if isinstance(expression_node, ast.Attribute):
        return expression_node.attr
    return None


def extract_path_variables(endpoint_key: str) -> list[str]:
    """Extract bracketed path variables from an endpoint key."""
    found_variables = re.findall(r"\[([^\]]+)\]", endpoint_key)
    seen: set[str] = set()
    unique: list[str] = []
    for variable_name in found_variables:
        if variable_name not in seen:
            seen.add(variable_name)
            unique.append(variable_name)
    return unique


def is_dynamic_endpoint_key(endpoint_key: str) -> bool:
    """Return True if the endpoint key contains dynamic segments."""
    return bool(DYNAMIC_SEGMENT_REGEX.search(endpoint_key))


def endpoint_key_to_template_literal_key(endpoint_key: str) -> str:
    """Convert a dynamic endpoint key into a TS template literal key."""
    # "notes.[test].get" -> `notes.${string}.get`
    template_key = DYNAMIC_SEGMENT_REGEX.sub(r"${string}", endpoint_key)
    return f"`{template_key}`"


def build_dynamic_template_index(
    dynamic_endpoint_keys: list[str],
    endpoint_source_files_by_key: dict[str, Path],
) -> dict[str, str]:
    """
    Returns a mapping of:
      template_literal_key -> original_dynamic_endpoint_key

    Errors if two different dynamic keys produce the same template key.
    Example collision:
      "notes.[test].get" and "notes.[id].get" => both `notes.${string}.get`
    """
    original_key_by_template_key: dict[str, str] = {}

    for original_endpoint_key in sorted(dynamic_endpoint_keys):
        template_literal_key = endpoint_key_to_template_literal_key(original_endpoint_key)
        existing_original_key = original_key_by_template_key.get(template_literal_key)

        if existing_original_key and existing_original_key != original_endpoint_key:
            existing_source = endpoint_source_files_by_key.get(existing_original_key)
            new_source = endpoint_source_files_by_key.get(original_endpoint_key)

            existing_source_display = str(existing_source) if existing_source else "<unknown file>"
            new_source_display = str(new_source) if new_source else "<unknown file>"

            raise RuntimeError(
                "Dynamic endpoint template collision detected.\n"
                f"Both endpoints produce the same key pattern: {template_literal_key}\n"
                f" - {existing_original_key}  (from {existing_source_display})\n"
                f" - {original_endpoint_key}  (from {new_source_display})\n"
                "These routes are the same shape. Keep only one. (Variable names inside [] do not differentiate routes.)"
            )

        original_key_by_template_key[template_literal_key] = original_endpoint_key

    return original_key_by_template_key

def normalize_annotation_for_signature(annotation_node: ast.expr | None) -> str:
    """Normalize annotation nodes for structural signature comparisons."""
    if annotation_node is None:
        return "<none>"
    try:
        return ast.unparse(annotation_node)
    except Exception:
        # stable-ish fallback
        return ast.dump(annotation_node, include_attributes=False)

def collect_dataclass_base_names(dataclass_node: ast.ClassDef) -> list[str]:
    """Return base class names for a dataclass AST node."""
    base_names: list[str] = []
    for base_expression in dataclass_node.bases:
        base_name = name_of_ast_expression(base_expression)
        if base_name is None and isinstance(base_expression, ast.Subscript):
            base_name = name_of_ast_expression(base_expression.value)
        if base_name is not None:
            base_names.append(base_name)
    return base_names


def build_dataclass_shape_signature(dataclass_node: ast.ClassDef) -> tuple[tuple[str, str], ...]:
    """
    A structural signature for a dataclass: (field_name, annotation_text) sorted by field_name.
    """
    field_definitions = collect_dataclass_fields(dataclass_node)
    signature_pairs: list[tuple[str, str]] = []
    base_names = collect_dataclass_base_names(dataclass_node)
    if base_names:
        signature_pairs.append(("__bases__", "|".join(base_names)))
    for field_name, annotation_node in field_definitions:
        signature_pairs.append((field_name, normalize_annotation_for_signature(annotation_node)))
    signature_pairs.sort(key=lambda pair: pair[0])
    return tuple(signature_pairs)



# ============================================================
# Decorator instance + extraction (registry routing uses .decorator_name)
# ============================================================

@dataclass(frozen=True)
class DecoratorInstance:
    """Captured metadata for a decorator expression in the AST."""
    decorator_name: str
    decorator_expression: ast.expr
    call_node: ast.Call | None
    positional_args: list[ast.expr]
    keyword_args: dict[str, ast.expr]


def extract_decorator_instance(decorator_expression: ast.expr) -> DecoratorInstance:
    """Parse a decorator expression into a normalized structure."""
    call_node: ast.Call | None = decorator_expression if isinstance(decorator_expression, ast.Call) else None
    callable_expression = call_node.func if call_node else decorator_expression

    decorator_name = "unknown"
    if isinstance(callable_expression, ast.Name):
        decorator_name = callable_expression.id
    elif isinstance(callable_expression, ast.Attribute):
        decorator_name = callable_expression.attr

    positional_args: list[ast.expr] = list(call_node.args) if call_node else []
    keyword_args: dict[str, ast.expr] = {}

    if call_node:
        for keyword_node in call_node.keywords:
            if keyword_node.arg is None:
                # **kwargs - ignore
                continue
            keyword_args[keyword_node.arg] = keyword_node.value

    return DecoratorInstance(
        decorator_name=decorator_name,
        decorator_expression=decorator_expression,
        call_node=call_node,
        positional_args=positional_args,
        keyword_args=keyword_args,
    )


# ============================================================
# AST collection helpers
# ============================================================

def is_dataclass_decorator_expression(decorator_expression: ast.expr) -> bool:
    """
    Matches:
      @dataclass
      @dataclasses.dataclass
      @dataclass(...)
      @dataclasses.dataclass(...)
    """
    if isinstance(decorator_expression, ast.Name) and decorator_expression.id == "dataclass":
        return True
    if isinstance(decorator_expression, ast.Attribute) and decorator_expression.attr == "dataclass":
        return True
    if isinstance(decorator_expression, ast.Call):
        return is_dataclass_decorator_expression(decorator_expression.func)
    return False


def collect_dataclass_class_nodes(module_node: ast.Module) -> dict[str, ast.ClassDef]:
    """Collect top-level dataclass class definitions by name."""
    dataclass_nodes_by_name: dict[str, ast.ClassDef] = {}
    for top_level_node in module_node.body:
        if not isinstance(top_level_node, ast.ClassDef):
            continue
        if any(is_dataclass_decorator_expression(dec) for dec in top_level_node.decorator_list):
            dataclass_nodes_by_name[top_level_node.name] = top_level_node
    return dataclass_nodes_by_name


def collect_dataclass_fields(dataclass_node: ast.ClassDef) -> list[tuple[str, ast.expr]]:
    """Collect annotated fields declared on a dataclass."""
    field_definitions: list[tuple[str, ast.expr]] = []
    for class_statement in dataclass_node.body:
        if isinstance(class_statement, ast.AnnAssign) and isinstance(class_statement.target, ast.Name):
            if class_statement.annotation is not None:
                field_definitions.append((class_statement.target.id, class_statement.annotation))
    return field_definitions

def collect_dataclass_fields_including_bases(
    dataclass_node: ast.ClassDef,
    *,
    symbol_index: "SymbolIndex",
) -> list[tuple[str, ast.expr]]:
    """Collect fields from a dataclass including inherited base fields."""
    fields_by_name: dict[str, ast.expr] = {}
    field_order: list[str] = []

    def add_fields(field_definitions: list[tuple[str, ast.expr]]) -> None:
        """Merge field definitions into the ordered field map."""
        for field_name, annotation_node in field_definitions:
            if field_name not in fields_by_name:
                field_order.append(field_name)
            fields_by_name[field_name] = annotation_node

    def visit(node: ast.ClassDef, *, resolving: set[str]) -> None:
        """Depth-first walk of base classes to accumulate inherited fields."""
        for base_name in collect_dataclass_base_names(node):
            base_metadata = symbol_index.dataclasses_by_name.get(base_name)
            if base_metadata is None:
                continue
            if base_name in resolving:
                continue
            resolving.add(base_name)
            visit(base_metadata.class_node, resolving=resolving)
            add_fields(collect_dataclass_fields(base_metadata.class_node))
            resolving.remove(base_name)

    visit(dataclass_node, resolving=set())
    add_fields(collect_dataclass_fields(dataclass_node))
    return [(field_name, fields_by_name[field_name]) for field_name in field_order]


def collect_route_methods(module_node: ast.Module, route_class_name: str) -> dict[str, ast.FunctionDef]:
    """Collect public methods from the configured route class."""
    for top_level_node in module_node.body:
        if isinstance(top_level_node, ast.ClassDef) and top_level_node.name == route_class_name:
            methods_by_name: dict[str, ast.FunctionDef] = {}
            for class_statement in top_level_node.body:
                if isinstance(class_statement, ast.FunctionDef) and not class_statement.name.startswith("_"):
                    methods_by_name[class_statement.name] = class_statement
            return methods_by_name
    return {}


def collect_type_aliases(module_node: ast.Module) -> dict[str, ast.expr]:
    """
    Supports:
      Python 3.12+:  type NoteId = int
      Also:          NoteId: TypeAlias = int
    """
    aliases_by_name: dict[str, ast.expr] = {}
    type_alias_node_type = getattr(ast, "TypeAlias", None)

    for top_level_node in module_node.body:
        if type_alias_node_type is not None and isinstance(top_level_node, type_alias_node_type):
            alias_name_node = getattr(top_level_node, "name", None)
            if isinstance(alias_name_node, ast.Name):
                aliases_by_name[alias_name_node.id] = top_level_node.value
            elif isinstance(alias_name_node, str):
                aliases_by_name[alias_name_node] = top_level_node.value
            continue

        if (
            isinstance(top_level_node, ast.AnnAssign)
            and isinstance(top_level_node.target, ast.Name)
            and top_level_node.value is not None
        ):
            annotation_name = name_of_ast_expression(top_level_node.annotation)
            if annotation_name == "TypeAlias":
                aliases_by_name[top_level_node.target.id] = top_level_node.value

    return aliases_by_name


def collect_method_parameters(
    function_node: ast.FunctionDef,
) -> list[tuple[str, ast.expr | None, bool, ast.expr | None]]:
    """
    Returns list of:
      (parameter_name, annotation_or_None, has_default_value, default_expr_or_None)
    for all params after self/cls.
    """
    collected_parameters: list[tuple[str, ast.expr | None, bool, ast.expr | None]] = []

    positional_parameters = list(function_node.args.posonlyargs) + list(function_node.args.args)
    default_expressions = list(function_node.args.defaults)
    first_default_index = len(positional_parameters) - len(default_expressions)

    for parameter_index, parameter_node in enumerate(positional_parameters):
        if parameter_index == 0 and parameter_node.arg in ("self", "cls"):
            continue

        has_default_value = parameter_index >= first_default_index and len(default_expressions) > 0
        default_expr_node = default_expressions[parameter_index - first_default_index] if has_default_value else None
        collected_parameters.append((parameter_node.arg, parameter_node.annotation, has_default_value, default_expr_node))

    for keyword_parameter_node, keyword_default_expr in zip(function_node.args.kwonlyargs, function_node.args.kw_defaults):
        has_default_value = keyword_default_expr is not None
        collected_parameters.append(
            (keyword_parameter_node.arg, keyword_parameter_node.annotation, has_default_value, keyword_default_expr)
        )

    return collected_parameters


# ============================================================
# Type translation
# ============================================================

@dataclass
class PythonToTypeScriptTypeTranslator:
    """Translate Python AST type annotations into TypeScript type strings."""
    config: TypeScriptGeneratorConfig
    known_dataclass_names: set[str]
    alias_definitions: dict[str, ast.expr]

    def to_typescript_type(
        self,
        annotation_node: ast.expr,
        referenced_dataclass_names: set[str],
        referenced_alias_names: set[str],
        referenced_passthrough_generic_arity: dict[str, int] | None = None,
        *,
        preserve_alias_symbols: bool = True,
        resolving_alias_names: Optional[set[str]] = None,
    ) -> str:
        """Translate a Python annotation AST node into a TS type string."""
        if resolving_alias_names is None:
            resolving_alias_names = set()

        # PEP604 unions: A | B
        if isinstance(annotation_node, ast.BinOp) and isinstance(annotation_node.op, ast.BitOr):
            left_type = self.to_typescript_type(
                annotation_node.left,
                referenced_dataclass_names,
                referenced_alias_names,
                referenced_passthrough_generic_arity,
                preserve_alias_symbols=preserve_alias_symbols,
                resolving_alias_names=resolving_alias_names,
            )
            right_type = self.to_typescript_type(
                annotation_node.right,
                referenced_dataclass_names,
                referenced_alias_names,
                referenced_passthrough_generic_arity,
                preserve_alias_symbols=preserve_alias_symbols,
                resolving_alias_names=resolving_alias_names,
            )
            return f"{left_type} | {right_type}"

        # Names: primitives, aliases, dataclasses
        if isinstance(annotation_node, ast.Name):
            python_type_name = annotation_node.id

            # Type alias
            if python_type_name in self.alias_definitions:
                if preserve_alias_symbols:
                    referenced_alias_names.add(python_type_name)
                    return python_type_name

                if python_type_name in resolving_alias_names:
                    return "unknown"

                resolving_alias_names.add(python_type_name)
                resolved_type = self.to_typescript_type(
                    self.alias_definitions[python_type_name],
                    referenced_dataclass_names,
                    referenced_alias_names,
                    referenced_passthrough_generic_arity,
                    preserve_alias_symbols=False,
                    resolving_alias_names=resolving_alias_names,
                )
                resolving_alias_names.remove(python_type_name)
                return resolved_type

            # Dataclass
            if python_type_name in self.known_dataclass_names:
                referenced_dataclass_names.add(python_type_name)
                # IMPORTANT: always reference the exported/public name (not the internal interface)
                return python_type_name

            # Primitive fallback
            return self.config.primitive_type_map.get(python_type_name, python_type_name)

        # None literal
        if isinstance(annotation_node, ast.Constant) and annotation_node.value is None:
            return "null"

        # Generics: list[T], dict[K,V], Optional[T], Union[...]
        if isinstance(annotation_node, ast.Subscript):
            generic_base_name = name_of_ast_expression(annotation_node.value) or "unknown"
            generic_base_name = self.config.typing_container_aliases.get(generic_base_name, generic_base_name)

            if isinstance(annotation_node.slice, ast.Tuple):
                generic_arguments = list(annotation_node.slice.elts)
            else:
                generic_arguments = [annotation_node.slice]

            if (
                referenced_passthrough_generic_arity is not None
                and isinstance(annotation_node.value, ast.Attribute)
                and isinstance(annotation_node.value.value, ast.Name)
                and annotation_node.value.value.id in self.config.passthrough_generic_modules
            ):
                passthrough_name = annotation_node.value.attr
                existing_arity = referenced_passthrough_generic_arity.get(passthrough_name, 0)
                referenced_passthrough_generic_arity[passthrough_name] = max(
                    existing_arity, len(generic_arguments)
                )

            arg_types = [
                self.to_typescript_type(
                    argument_node,
                    referenced_dataclass_names,
                    referenced_alias_names,
                    referenced_passthrough_generic_arity,
                    preserve_alias_symbols=preserve_alias_symbols,
                    resolving_alias_names=resolving_alias_names,
                )
                for argument_node in generic_arguments
            ]

            template_spec = self.config.generic_type_map.get(generic_base_name)
            if template_spec is not None:
                param_names, template = template_spec
                if len(arg_types) == len(param_names):
                    rendered = template
                    if "{T}" in rendered:
                        rendered = rendered.replace("{T}", arg_types[0] if arg_types else "unknown")
                    for index, arg_type in enumerate(arg_types, start=1):
                        rendered = rendered.replace(f"{{T{index}}}", arg_type)
                    for param_name, arg_type in zip(param_names, arg_types):
                        rendered = rendered.replace(f"{{{param_name}}}", arg_type)
                    return rendered

            if generic_base_name in ("list", "set", "Sequence", "Iterable"):
                inner_type = (
                    arg_types[0] if arg_types else "unknown"
                )
                return f"{inner_type}[]"

            if generic_base_name == "dict":
                key_type = (
                    arg_types[0] if len(arg_types) > 0 else "string"
                )
                value_type = (
                    arg_types[1] if len(arg_types) > 1 else "unknown"
                )
                if key_type not in ("string", "number"):
                    key_type = "string"
                return f"Record<{key_type}, {value_type}>"

            if generic_base_name == "tuple":
                tuple_types = ", ".join(
                    arg_types
                )
                return f"[{tuple_types}]"

            if generic_base_name == "optional":
                inner_type = (
                    arg_types[0] if arg_types else "unknown"
                )
                return f"{inner_type} | null"

            if generic_base_name == "union":
                union_types = " | ".join(
                    arg_types
                )
                return union_types or "unknown"

            generic_types = ", ".join(
                arg_types
            )
            return f"{generic_base_name}<{generic_types}>"

        # Fallback
        try:
            unparsed = ast.unparse(annotation_node)
            return self.config.primitive_type_map.get(unparsed, "unknown")
        except Exception:
            return "unknown"


# ============================================================
# Metadata + state
# ============================================================

@dataclass(frozen=True)
class ParsedPythonFile:
    """Parsed Python file paired with its AST module node."""
    file_path: Path
    module_node: ast.Module


@dataclass(frozen=True)
class DataclassMetadata:
    """Metadata for a discovered dataclass in the AST."""
    class_name: str
    class_node: ast.ClassDef
    source_file: Path


@dataclass(frozen=True)
class EndpointMetadata:
    """Metadata describing a routed endpoint method."""
    endpoint_key: str
    method_name: str
    file_stem: str
    source_file: Path
    function_node: ast.FunctionDef


@dataclass
class SymbolIndex:
    """Index of discovered dataclasses and aliases across parsed files."""
    dataclasses_by_name: dict[str, DataclassMetadata] = field(default_factory=dict)
    aliases_by_name: dict[str, ast.expr] = field(default_factory=dict)
    dataclass_sources: dict[str, Path] = field(default_factory=dict)
    alias_sources: dict[str, Path] = field(default_factory=dict)

    # ✅ new: structural signatures to validate duplicates
    dataclass_signatures_by_name: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)

    # ✅ optional: track duplicate sources (useful for debugging)
    dataclass_duplicate_sources_by_name: dict[str, list[Path]] = field(default_factory=dict)



# ---- specs for codegen blocks so maps can reference *public* names ----

ParameterDefinition = tuple[str, ast.expr | None, bool, ast.expr | None]


@dataclass(frozen=True)
class ParameterInterfaceSpec:
    """Spec for emitting request parameter interfaces."""
    export_name: str          # "NotesPostBody"
    interface_name: str       # "NotesPostBodyType"
    parameters: list[ParameterDefinition]


@dataclass(frozen=True)
class ResponseWrapperSpec:
    """Spec for emitting response wrapper interfaces."""
    export_name: str          # "NotesGet"
    interface_name: str       # "NotesGetType"
    base_dataclass_name: str  # "Notes"


@dataclass
class GeneratorState:
    """State container for the TypeScript generation pipeline."""
    config: TypeScriptGeneratorConfig
    parsed_files: list[ParsedPythonFile]
    symbol_index: SymbolIndex
    type_translator: PythonToTypeScriptTypeTranslator

    # For map emission order and completeness
    discovered_endpoint_keys: list[str] = field(default_factory=list)
    endpoint_source_files_by_key: dict[str, Path] = field(default_factory=dict)

    # Symbols referenced by translated types
    referenced_dataclass_names: set[str] = field(default_factory=set)
    referenced_alias_names: set[str] = field(default_factory=set)
    referenced_passthrough_generic_arity: dict[str, int] = field(default_factory=dict)

    # Per-endpoint map values should be *public exported names* (NOT internal interface names)
    endpoint_response_types: dict[str, str] = field(default_factory=dict)
    endpoint_body_types: dict[str, str] = field(default_factory=dict)
    endpoint_query_types: dict[str, str] = field(default_factory=dict)
    endpoint_path_variables: dict[str, list[str]] = field(default_factory=dict)

    # Specs to emit
    body_parameter_interfaces: dict[str, ParameterInterfaceSpec] = field(default_factory=dict)   # keyed by export_name
    query_parameter_interfaces: dict[str, ParameterInterfaceSpec] = field(default_factory=dict)  # keyed by export_name
    response_wrappers: dict[str, ResponseWrapperSpec] = field(default_factory=dict)              # keyed by export_name

    # Name reservation so maps never point at wrong name
    used_export_names: set[str] = field(default_factory=set)

    # Dataclass emission recursion guard
    emitted_dataclass_names: set[str] = field(default_factory=set)

    # Wrapper reuse guard (kept for compatibility; wrappers are unused by default now)
    wrapper_export_name_by_signature: dict[tuple[str, str], str] = field(default_factory=dict)

    # Example future extension bucket (authorized decorator)
    endpoint_authorization_roles: dict[str, str] = field(default_factory=dict)

    def reserve_export_name(self, preferred_export_name: str) -> str:
        """
        Returns a unique export symbol name and reserves it immediately.
        This is critical so:
          - emitters use the same name
          - maps reference the same name
        """
        if preferred_export_name not in self.used_export_names:
            self.used_export_names.add(preferred_export_name)
            return preferred_export_name

        suffix_number = 2
        while f"{preferred_export_name}{suffix_number}" in self.used_export_names:
            suffix_number += 1

        unique_name = f"{preferred_export_name}{suffix_number}"
        self.used_export_names.add(unique_name)
        return unique_name


# ============================================================
# Transformer registry (registry is the controller)
# ============================================================

ClassDecoratorTransformer = Callable[[DecoratorInstance, DataclassMetadata, GeneratorState], None]
MethodDecoratorTransformer = Callable[[DecoratorInstance, EndpointMetadata, GeneratorState], None]
MethodTransformer = Callable[[EndpointMetadata, GeneratorState], None]
StateEmitter = Callable[[GeneratorState], list[str]]


@dataclass
class TransformerRegistry:
    """Registry of transformers and emitters used by the pipeline."""
    class_decorator_transformers_by_name: dict[str, list[ClassDecoratorTransformer]] = field(default_factory=dict)
    method_decorator_transformers_by_name: dict[str, list[MethodDecoratorTransformer]] = field(default_factory=dict)

    method_transformers: list[MethodTransformer] = field(default_factory=list)
    state_emitters: list[StateEmitter] = field(default_factory=list)

    def add_class_decorator(self, decorator_name: str, transformer: ClassDecoratorTransformer) -> None:
        """Register a transformer for a class decorator name."""
        self.class_decorator_transformers_by_name.setdefault(decorator_name, []).append(transformer)

    def add_method_decorator(self, decorator_name: str, transformer: MethodDecoratorTransformer) -> None:
        """Register a transformer for a method decorator name."""
        self.method_decorator_transformers_by_name.setdefault(decorator_name, []).append(transformer)

    def add_method(self, transformer: MethodTransformer | StateEmitter) -> None:
        """Register a method transformer or a state emitter."""
        # Overload-ish: (EndpointMetadata, GeneratorState) vs (GeneratorState)->list[str]
        argument_count = getattr(getattr(transformer, "__code__", None), "co_argcount", None)
        if argument_count == 2:
            self.method_transformers.append(transformer)  # type: ignore[arg-type]
        else:
            self.state_emitters.append(transformer)       # type: ignore[arg-type]


# ============================================================
# Pipeline
# ============================================================

class Pipeline:
    """Pipeline to parse Python files and emit TypeScript typings."""
    @staticmethod
    def build_state(
        registry: TransformerRegistry,
        *,
        inputs: Iterable[str],
        config: TypeScriptGeneratorConfig,
        allowed_methods: set[str] | None = None,
        per_file_limit: int | None = None,
    ) -> GeneratorState:
        """Parse inputs and build the generator state."""
        python_files = Pipeline._collect_python_files(inputs)
        parsed_files = Pipeline._parse_python_files(python_files)
        symbol_index = Pipeline._build_symbol_index(parsed_files)

        type_translator = PythonToTypeScriptTypeTranslator(
            config=config,
            known_dataclass_names=set(symbol_index.dataclasses_by_name.keys()),
            alias_definitions=symbol_index.aliases_by_name,
        )

        generator_state = GeneratorState(
            config=config,
            parsed_files=parsed_files,
            symbol_index=symbol_index,
            type_translator=type_translator,
        )

        # Reserve dataclass export names up-front (prevents collisions later)
        for dataclass_name in sorted(symbol_index.dataclasses_by_name.keys()):
            generator_state.reserve_export_name(dataclass_name)

        endpoint_metadata_list = Pipeline._collect_endpoints(
            parsed_files,
            config=config,
            allowed_methods=allowed_methods,
            per_file_limit=per_file_limit,
        )
        generator_state.discovered_endpoint_keys = [endpoint.endpoint_key for endpoint in endpoint_metadata_list]

        endpoint_source_files_by_key: dict[str, Path] = {}
        for endpoint in endpoint_metadata_list:
            if endpoint.endpoint_key in endpoint_source_files_by_key:
                previous_source = endpoint_source_files_by_key[endpoint.endpoint_key]
                raise RuntimeError(
                    f"Endpoint key collision: {endpoint.endpoint_key} defined in both "
                    f"{previous_source} and {endpoint.source_file}."
                )
            endpoint_source_files_by_key[endpoint.endpoint_key] = endpoint.source_file
        generator_state.endpoint_source_files_by_key = endpoint_source_files_by_key

        # Dispatch class decorators
        for dataclass_metadata in symbol_index.dataclasses_by_name.values():
            for decorator_expression in dataclass_metadata.class_node.decorator_list:
                decorator_instance = extract_decorator_instance(decorator_expression)
                transformers = registry.class_decorator_transformers_by_name.get(decorator_instance.decorator_name, [])
                for transformer in transformers:
                    transformer(decorator_instance, dataclass_metadata, generator_state)

        # Dispatch method decorators + method transforms
        for endpoint_metadata in endpoint_metadata_list:
            for decorator_expression in endpoint_metadata.function_node.decorator_list:
                decorator_instance = extract_decorator_instance(decorator_expression)
                transformers = registry.method_decorator_transformers_by_name.get(decorator_instance.decorator_name, [])
                for transformer in transformers:
                    transformer(decorator_instance, endpoint_metadata, generator_state)

            for transformer in registry.method_transformers:
                transformer(endpoint_metadata, generator_state)

        return generator_state

    @staticmethod
    def emit_typescript(registry: TransformerRegistry, generator_state: GeneratorState) -> str:
        """Emit TypeScript output from a prepared generator state."""
        output_lines: list[str] = []
        for emitter in registry.state_emitters:
            output_lines.extend(emitter(generator_state))
        return "\n".join(output_lines).rstrip() + "\n"

    @staticmethod
    def run(
        registry: TransformerRegistry,
        *,
        inputs: Iterable[str],
        config: TypeScriptGeneratorConfig,
        allowed_methods: set[str] | None = None,
        per_file_limit: int | None = None,
    ) -> str:
        """Parse inputs and emit TypeScript in one step."""
        generator_state = Pipeline.build_state(
            registry,
            inputs=inputs,
            config=config,
            allowed_methods=allowed_methods,
            per_file_limit=per_file_limit,
        )
        return Pipeline.emit_typescript(registry, generator_state)

    # keep the rest of Pipeline (collect/parse/build_symbol_index/_collect_endpoints) unchanged

    @staticmethod
    def _collect_python_files(inputs: Iterable[str]) -> list[Path]:
        """Collect Python files from paths, directories, or globs."""
        discovered_files: list[Path] = []

        for raw_input in inputs:
            input_path = Path(raw_input)

            if input_path.exists() and input_path.is_dir():
                discovered_files.extend(sorted(input_path.rglob("*.py")))
                continue

            if input_path.exists() and input_path.is_file() and input_path.suffix == ".py":
                discovered_files.append(input_path)
                continue

            glob_matches = list(Path(".").glob(raw_input))
            if (
                not glob_matches
                and ("[" in raw_input or "]" in raw_input)
                and not any(wildcard_char in raw_input for wildcard_char in ("*", "?", "{"))
            ):
                escaped_pattern = glob_module.escape(raw_input)
                glob_matches = list(Path(".").glob(escaped_pattern))

            discovered_files.extend(sorted(match for match in glob_matches if match.suffix == ".py"))

        seen_resolved_paths: set[Path] = set()
        unique_files: list[Path] = []
        for file_path in discovered_files:
            resolved_path = file_path.resolve()
            if resolved_path not in seen_resolved_paths:
                seen_resolved_paths.add(resolved_path)
                unique_files.append(file_path)

        if not unique_files:
            raise SystemExit("No .py files found from inputs.")

        return unique_files

    @staticmethod
    def _parse_python_files(python_files: list[Path]) -> list[ParsedPythonFile]:
        """Parse each file into an AST module node."""
        parsed_files: list[ParsedPythonFile] = []
        for file_path in python_files:
            source_text = file_path.read_text(encoding="utf-8")
            try:
                module_node = ast.parse(source_text, filename=str(file_path))
            except SyntaxError as syntax_error:
                offending_line = source_text.splitlines()[syntax_error.lineno - 1] if syntax_error.lineno else ""
                raise RuntimeError(
                    f"{file_path}:{syntax_error.lineno}:{syntax_error.offset} {syntax_error.msg}\n{offending_line}"
                ) from syntax_error
            parsed_files.append(ParsedPythonFile(file_path=file_path, module_node=module_node))
        return parsed_files

    @staticmethod
    def _build_symbol_index(parsed_files: list[ParsedPythonFile]) -> SymbolIndex:
        """Build a symbol index of dataclasses and aliases."""
        symbol_index = SymbolIndex()

        for parsed_file in parsed_files:
            if parsed_file.file_path.name == "__init__.py":
                continue

            dataclass_nodes_by_name = collect_dataclass_class_nodes(parsed_file.module_node)
            for class_name, class_node in dataclass_nodes_by_name.items():
                if class_name in symbol_index.dataclasses_by_name:
                    existing_metadata = symbol_index.dataclasses_by_name[class_name]
                    existing_source = symbol_index.dataclass_sources[class_name]

                    existing_signature = symbol_index.dataclass_signatures_by_name.get(class_name)
                    new_signature = build_dataclass_shape_signature(class_node)

                    if existing_signature is None:
                        existing_signature = build_dataclass_shape_signature(existing_metadata.class_node)
                        symbol_index.dataclass_signatures_by_name[class_name] = existing_signature

                    # ✅ If identical, allow duplicate and record it (no error)
                    if existing_signature == new_signature:
                        symbol_index.dataclass_duplicate_sources_by_name.setdefault(class_name, []).append(parsed_file.file_path)
                        continue

                    # ❌ If different, error with better diagnostics
                    existing_line = getattr(existing_metadata.class_node, "lineno", "?")
                    new_line = getattr(class_node, "lineno", "?")

                    raise RuntimeError(
                        "Dataclass name collision with different shapes.\n"
                        f"Dataclass: {class_name}\n"
                        f" - {existing_source}:{existing_line} -> {existing_signature}\n"
                        f" - {parsed_file.file_path}:{new_line} -> {new_signature}\n"
                        "Fix: rename one dataclass, or move shared models into a single module and import them."
                    )

                if class_name in symbol_index.aliases_by_name:
                    previous_source = symbol_index.alias_sources[class_name]
                    raise RuntimeError(
                        f"Name collision: {class_name} is a type alias in {previous_source} and a dataclass in {parsed_file.file_path}."
                    )

                symbol_index.dataclasses_by_name[class_name] = DataclassMetadata(
                    class_name=class_name,
                    class_node=class_node,
                    source_file=parsed_file.file_path,
                )
                symbol_index.dataclass_sources[class_name] = parsed_file.file_path

            aliases_in_file = collect_type_aliases(parsed_file.module_node)
            for alias_name, alias_expr in aliases_in_file.items():
                if alias_name in symbol_index.aliases_by_name:
                    previous_source = symbol_index.alias_sources[alias_name]
                    raise RuntimeError(
                        f"Type alias collision: {alias_name} defined in both {previous_source} and {parsed_file.file_path}."
                    )
                if alias_name in symbol_index.dataclasses_by_name:
                    previous_source = symbol_index.dataclass_sources[alias_name]
                    raise RuntimeError(
                        f"Name collision: {alias_name} is a dataclass in {previous_source} and a type alias in {parsed_file.file_path}."
                    )

                symbol_index.aliases_by_name[alias_name] = alias_expr
                symbol_index.alias_sources[alias_name] = parsed_file.file_path

        return symbol_index

    @staticmethod
    def _collect_endpoints(
        parsed_files: list[ParsedPythonFile],
        *,
        config: TypeScriptGeneratorConfig,
        allowed_methods: set[str] | None,
        per_file_limit: int | None,
    ) -> list[EndpointMetadata]:
        """Collect Endpoint methods and build endpoint metadata."""
        collected_endpoints: list[EndpointMetadata] = []
        effective_allowed_methods = allowed_methods
        if effective_allowed_methods is None:
            effective_allowed_methods = set(config.http_methods)
            effective_allowed_methods.add("index")

        for parsed_file in parsed_files:
            if parsed_file.file_path.name == "__init__.py":
                continue

            methods_by_name = collect_route_methods(parsed_file.module_node, route_class_name=config.route_class_name)
            if not methods_by_name:
                continue

            sorted_methods = sorted(methods_by_name.items(), key=lambda item: item[0])
            if per_file_limit is not None:
                sorted_methods = sorted_methods[:per_file_limit]

            for original_method_name, function_node in sorted_methods:
                if effective_allowed_methods is not None and original_method_name not in effective_allowed_methods:
                    continue

                effective_method_name = original_method_name
                if original_method_name == "index" and config.index_method_alias:
                    effective_method_name = config.index_method_alias

                file_stem = parsed_file.file_path.stem
                endpoint_key = (
                    file_stem
                    if (original_method_name == "index" and not config.index_method_alias)
                    else f"{file_stem}.{effective_method_name}"
                )

                collected_endpoints.append(
                    EndpointMetadata(
                        endpoint_key=endpoint_key,
                        method_name=effective_method_name,
                        file_stem=file_stem,
                        source_file=parsed_file.file_path,
                        function_node=function_node,
                    )
                )

        return collected_endpoints


# ============================================================
# Shared emit helpers (emit specs)
# ============================================================

def ensure_relative_typescript_import_path(import_path: str) -> str:
    """
    Ensures TS import is relative-ish:
      "api.types" -> "./api.types"
      "../api.types" -> "../api.types"
      "./api.types" -> "./api.types"
    """
    if import_path.startswith("./") or import_path.startswith("../"):
        return import_path
    return f"./{import_path}"


def compute_typescript_import_path_without_extension(from_file: Path, to_file: Path) -> str:
    """
    Returns a TS module path from from_file -> to_file, WITHOUT the ".ts" extension.
    Example: ./api.types
    """
    from_directory = from_file.parent
    to_path_without_extension = to_file.with_suffix("")  # drop ".ts"

    relative_path = os.path.relpath(to_path_without_extension, start=from_directory)
    module_path = Path(relative_path).as_posix()
    return ensure_relative_typescript_import_path(module_path)


def collect_contract_export_names(generator_state: GeneratorState) -> list[str]:
    """Collect exported symbol names for the contracts module."""
    value_export_names: set[str] = set()

    value_export_names.update(generator_state.emitted_dataclass_names)
    value_export_names.update(generator_state.body_parameter_interfaces.keys())
    value_export_names.update(generator_state.query_parameter_interfaces.keys())
    value_export_names.update(generator_state.response_wrappers.keys())

    return sorted(value_export_names)



def render_contracts_typescript_file(generator_state: GeneratorState, *, types_module_path: str) -> str:
    """Render the re-export contracts TypeScript file."""
    value_exports = collect_contract_export_names(generator_state)

    output_lines: list[str] = []
    output_lines.append("// api.contracts.ts (AUTOGENERATED)")
    output_lines.append("")

    if value_exports:
        output_lines.append("export {")
        for export_name in value_exports:
            output_lines.append(f"  {export_name},")
        output_lines.append(f'}} from "{types_module_path}";')
        output_lines.append("")
        output_lines.append("")

    return "\n".join(output_lines).rstrip() + "\n"



def emit_parameter_interface_spec(generator_state: GeneratorState, spec: ParameterInterfaceSpec) -> list[str]:
    """Emit TypeScript for a parameter interface and struct helper."""
    type_translator = generator_state.type_translator

    output_lines: list[str] = []
    output_lines.append(f"interface {spec.interface_name} {{")

    for parameter_name, annotation_node, has_default_value, default_expr_node in spec.parameters:
        if annotation_node is None:
            parameter_typescript_type = "unknown"
        else:
            parameter_typescript_type = type_translator.to_typescript_type(
                annotation_node,
                generator_state.referenced_dataclass_names,
                generator_state.referenced_alias_names,
                generator_state.referenced_passthrough_generic_arity,
            )

        optional_marker = "?" if has_default_value else ""

        if (
            has_default_value
            and isinstance(default_expr_node, ast.Constant)
            and default_expr_node.value is None
            and "null" not in parameter_typescript_type
        ):
            parameter_typescript_type = f"{parameter_typescript_type} | null"

        output_lines.append(f"  {parameter_name}{optional_marker}: {parameter_typescript_type};")

    output_lines.append("}")

    keys_literal = ", ".join(f'"{parameter_name}"' for (parameter_name, _, _, _) in spec.parameters)
    output_lines.append(f"export const {spec.export_name} = struct<{spec.interface_name}>()({keys_literal});")
    output_lines.append(f"export type {spec.export_name} = {spec.interface_name};")
    output_lines.append("")
    output_lines.append("")
    return output_lines


def emit_dataclass_interface_lines(generator_state: GeneratorState, dataclass_name: str) -> list[str]:
    """Emit TypeScript for a dataclass definition and dependencies."""
    config = generator_state.config
    type_translator = generator_state.type_translator
    symbol_index = generator_state.symbol_index

    if dataclass_name in generator_state.emitted_dataclass_names:
        return []

    dataclass_metadata = symbol_index.dataclasses_by_name.get(dataclass_name)
    if dataclass_metadata is None:
        return []

    generator_state.emitted_dataclass_names.add(dataclass_name)

    field_definitions = collect_dataclass_fields_including_bases(
        dataclass_metadata.class_node,
        symbol_index=symbol_index,
    )

    dependency_dataclass_names: set[str] = set()
    dependency_alias_names: set[str] = set()
    for _, field_annotation_node in field_definitions:
        type_translator.to_typescript_type(
            field_annotation_node,
            dependency_dataclass_names,
            dependency_alias_names,
            generator_state.referenced_passthrough_generic_arity,
        )

    output_lines: list[str] = []
    for dependency_dataclass_name in sorted(dependency_dataclass_names):
        output_lines.extend(emit_dataclass_interface_lines(generator_state, dependency_dataclass_name))

    interface_name = to_typescript_type_symbol(config, dataclass_name)

    output_lines.append(f"interface {interface_name} {{")
    for field_name, field_annotation_node in field_definitions:
        field_typescript_type = type_translator.to_typescript_type(
            field_annotation_node,
            generator_state.referenced_dataclass_names,
            generator_state.referenced_alias_names,
            generator_state.referenced_passthrough_generic_arity,
        )
        output_lines.append(f"  {field_name}: {field_typescript_type};")
    output_lines.append("}")

    keys_literal = ", ".join(f'"{field_name}"' for (field_name, _) in field_definitions)
    output_lines.append(f"export const {dataclass_name} = struct<{interface_name}>()({keys_literal});")
    output_lines.append(f"export type {dataclass_name} = {interface_name};")
    output_lines.append("")
    output_lines.append("")
    return output_lines


def emit_response_wrapper_spec(generator_state: GeneratorState, spec: ResponseWrapperSpec) -> list[str]:
    """Emit TypeScript for a response wrapper interface."""
    # Wrappers are not used by default now, but keeping the mechanism for future extensions.
    config = generator_state.config
    type_translator = generator_state.type_translator
    symbol_index = generator_state.symbol_index

    output_lines: list[str] = []
    output_lines.extend(emit_dataclass_interface_lines(generator_state, spec.base_dataclass_name))

    base_dataclass_metadata = symbol_index.dataclasses_by_name.get(spec.base_dataclass_name)
    if base_dataclass_metadata is None:
        return output_lines

    field_definitions = collect_dataclass_fields_including_bases(
        base_dataclass_metadata.class_node,
        symbol_index=symbol_index,
    )

    output_lines.append(f"interface {spec.interface_name} {{")
    for field_name, field_annotation_node in field_definitions:
        field_typescript_type = type_translator.to_typescript_type(
            field_annotation_node,
            generator_state.referenced_dataclass_names,
            generator_state.referenced_alias_names,
            generator_state.referenced_passthrough_generic_arity,
        )
        output_lines.append(f"  {field_name}: {field_typescript_type};")
    output_lines.append("}")

    keys_literal = ", ".join(f'"{field_name}"' for (field_name, _) in field_definitions)
    output_lines.append(f"export const {spec.export_name} = struct<{spec.interface_name}>()({keys_literal});")
    output_lines.append(f"export type {spec.export_name} = {spec.interface_name};")
    output_lines.append("")
    output_lines.append("")
    return output_lines


# ============================================================
# Built-in method decorator transformer: @endpoints.params(...)
# ============================================================

def parse_query_params_from_params_decorator(
    decorator_instance: DecoratorInstance,
) -> list[ParameterDefinition]:
    """
    Accepts:
      @endpoints.params({"dry_run": bool})
      @endpoints.params({"dry_run": (bool, False)})
    Produces:
      (name, annotation, has_default, default_expr)
    """
    if not decorator_instance.positional_args:
        return []

    first_argument = decorator_instance.positional_args[0]
    if not isinstance(first_argument, ast.Dict):
        return []

    parsed_parameters: list[ParameterDefinition] = []

    for dict_key_node, dict_value_node in zip(first_argument.keys, first_argument.values):
        if not (isinstance(dict_key_node, ast.Constant) and isinstance(dict_key_node.value, str)):
            continue

        parameter_name = dict_key_node.value

        annotation_node: ast.expr | None = None
        has_default_value = False
        default_value_node: ast.expr | None = None

        if isinstance(dict_value_node, ast.Tuple) and len(dict_value_node.elts) == 2:
            annotation_node = dict_value_node.elts[0] if isinstance(dict_value_node.elts[0], ast.expr) else None
            default_value_node = dict_value_node.elts[1] if isinstance(dict_value_node.elts[1], ast.expr) else None
            has_default_value = True
        elif isinstance(dict_value_node, ast.expr):
            annotation_node = dict_value_node

        parsed_parameters.append((parameter_name, annotation_node, has_default_value, default_value_node))

    return parsed_parameters


def transform_collect_endpoint_query_params_from_decorator(
    decorator_instance: DecoratorInstance,
    endpoint_metadata: EndpointMetadata,
    generator_state: GeneratorState,
) -> None:
    """Record query parameter types declared via @params decorator."""
    config = generator_state.config
    type_translator = generator_state.type_translator

    if not config.emit_query_params:
        return

    parsed_query_parameters = parse_query_params_from_params_decorator(decorator_instance)
    if not parsed_query_parameters:
        return

    preferred_export_name = (
        f"{to_pascal_case(endpoint_metadata.file_stem)}{to_pascal_case(endpoint_metadata.method_name)}Query"
    )
    export_name = generator_state.reserve_export_name(preferred_export_name)
    interface_name = to_typescript_type_symbol(config, export_name)

    spec = ParameterInterfaceSpec(
        export_name=export_name,
        interface_name=interface_name,
        parameters=parsed_query_parameters,
    )

    generator_state.query_parameter_interfaces[export_name] = spec
    generator_state.endpoint_query_types[endpoint_metadata.endpoint_key] = export_name

    for _, annotation_node, _, _ in parsed_query_parameters:
        if annotation_node is None:
            continue
        type_translator.to_typescript_type(
            annotation_node,
            generator_state.referenced_dataclass_names,
            generator_state.referenced_alias_names,
            generator_state.referenced_passthrough_generic_arity,
        )


# ============================================================
# Built-in method transforms
# ============================================================

def get_query_param_names_for_endpoint(generator_state: GeneratorState, endpoint_key: str) -> set[str]:
    """Return the set of query parameter names for an endpoint."""
    export_name = generator_state.endpoint_query_types.get(endpoint_key)
    if not export_name:
        return set()

    spec = generator_state.query_parameter_interfaces.get(export_name)
    if not spec:
        return set()

    return {parameter_name for (parameter_name, _, _, _) in spec.parameters}


def transform_set_query_params_default_never(endpoint_metadata: EndpointMetadata, generator_state: GeneratorState) -> None:
    """Ensure endpoints default to never for query params when none are defined."""
    config = generator_state.config
    if not config.emit_query_params:
        return
    endpoint_key = endpoint_metadata.endpoint_key
    if endpoint_key not in generator_state.endpoint_query_types:
        generator_state.endpoint_query_types[endpoint_key] = "never"


def transform_collect_endpoint_body_params_from_signature(endpoint_metadata: EndpointMetadata, generator_state: GeneratorState) -> None:
    """Collect request body parameters from endpoint method signatures."""
    config = generator_state.config
    type_translator = generator_state.type_translator

    signature_parameters = collect_method_parameters(endpoint_metadata.function_node)
    query_param_names = get_query_param_names_for_endpoint(generator_state, endpoint_metadata.endpoint_key)

    body_parameters = [
        parameter_tuple
        for parameter_tuple in signature_parameters
        if parameter_tuple[0] not in query_param_names
    ]

    if endpoint_metadata.method_name in config.body_methods:
        preferred_export_name = f"{to_pascal_case(endpoint_metadata.file_stem)}{to_pascal_case(endpoint_metadata.method_name)}Body"
        export_name = generator_state.reserve_export_name(preferred_export_name)
        interface_name = to_typescript_type_symbol(config, export_name)

        spec = ParameterInterfaceSpec(
            export_name=export_name,
            interface_name=interface_name,
            parameters=body_parameters,
        )

        generator_state.body_parameter_interfaces[export_name] = spec
        generator_state.endpoint_body_types[endpoint_metadata.endpoint_key] = export_name

        for _, annotation_node, _, _ in body_parameters:
            if annotation_node is None:
                continue
            type_translator.to_typescript_type(
                annotation_node,
                generator_state.referenced_dataclass_names,
                generator_state.referenced_alias_names,
                generator_state.referenced_passthrough_generic_arity,
            )
        return

    if config.include_never_for_non_body:
        generator_state.endpoint_body_types[endpoint_metadata.endpoint_key] = "never"


def transform_collect_endpoint_response_types(endpoint_metadata: EndpointMetadata, generator_state: GeneratorState) -> None:
    """Collect response type mappings for endpoint methods."""
    config = generator_state.config
    type_translator = generator_state.type_translator
    known_dataclass_names = set(generator_state.symbol_index.dataclasses_by_name.keys())

    endpoint_key = endpoint_metadata.endpoint_key
    method_name = endpoint_metadata.method_name

    # For body methods, Endpoints maps to the BODY type (legacy behavior)
    if method_name in config.body_methods:
        body_export_type = generator_state.endpoint_body_types.get(endpoint_key)
        if not body_export_type:
            body_export_type = "never" if config.include_never_for_non_body else "unknown"
        generator_state.endpoint_response_types[endpoint_key] = body_export_type
        return

    return_annotation = endpoint_metadata.function_node.returns
    if return_annotation is None:
        generator_state.endpoint_response_types[endpoint_key] = "unknown"
        return

    # If returning a dataclass, reference exported dataclass name directly (no wrapper)
    if isinstance(return_annotation, ast.Name) and return_annotation.id in known_dataclass_names:
        dataclass_name = return_annotation.id
        generator_state.referenced_dataclass_names.add(dataclass_name)
        generator_state.endpoint_response_types[endpoint_key] = dataclass_name
        return

    translated_return_type = type_translator.to_typescript_type(
        return_annotation,
        generator_state.referenced_dataclass_names,
        generator_state.referenced_alias_names,
        generator_state.referenced_passthrough_generic_arity,
    )
    if translated_return_type == "null":
        translated_return_type = "void"

    generator_state.endpoint_response_types[endpoint_key] = translated_return_type


def transform_collect_endpoint_path_variables(endpoint_metadata: EndpointMetadata, generator_state: GeneratorState) -> None:
    """Collect path parameter names from dynamic endpoint keys."""
    config = generator_state.config
    if not config.emit_path_params:
        return

    path_variable_names = extract_path_variables(endpoint_metadata.endpoint_key)
    if not path_variable_names:
        return

    generator_state.endpoint_path_variables[endpoint_metadata.endpoint_key] = path_variable_names


# ============================================================
# Emit blocks (state emitters)
# ============================================================

def emit_imports_section(generator_state: GeneratorState) -> list[str]:
    """Emit shared imports for the generated TypeScript file."""
    return [
        'import { struct } from "tsunami";',
        "",
        "",
    ]


def emit_referenced_dataclasses_section(generator_state: GeneratorState) -> list[str]:
    """Emit all referenced dataclass interfaces."""
    output_lines: list[str] = []
    for dataclass_name in sorted(generator_state.referenced_dataclass_names):
        output_lines.extend(emit_dataclass_interface_lines(generator_state, dataclass_name))
    return output_lines


def emit_response_wrappers_section(generator_state: GeneratorState) -> list[str]:
    """Emit response wrapper interfaces when configured."""
    # By default you won't have wrappers now; kept for future extension compatibility.
    output_lines: list[str] = []
    for export_name, wrapper_spec in sorted(generator_state.response_wrappers.items(), key=lambda item: item[0]):
        output_lines.extend(emit_response_wrapper_spec(generator_state, wrapper_spec))
    return output_lines


def emit_referenced_aliases_section(generator_state: GeneratorState) -> list[str]:
    """Emit referenced type aliases translated to TypeScript."""
    if not generator_state.referenced_alias_names:
        return []

    symbol_index = generator_state.symbol_index
    type_translator = generator_state.type_translator

    output_lines: list[str] = []
    for alias_name in sorted(generator_state.referenced_alias_names):
        alias_expression = symbol_index.aliases_by_name.get(alias_name)
        if alias_expression is None:
            continue

        resolved_alias_type = type_translator.to_typescript_type(
            alias_expression,
            generator_state.referenced_dataclass_names,
            generator_state.referenced_alias_names,
            generator_state.referenced_passthrough_generic_arity,
            preserve_alias_symbols=False,
        )
        output_lines.append(f"export type {alias_name} = {resolved_alias_type};")

    output_lines.append("")
    output_lines.append("")
    return output_lines


def emit_passthrough_generic_types_section(generator_state: GeneratorState) -> list[str]:
    """Emit passthrough generic type helpers for unmodeled generics."""
    passthrough = generator_state.referenced_passthrough_generic_arity
    if not passthrough:
        return []

    output_lines: list[str] = []
    for name in sorted(passthrough):
        arity = passthrough[name] or 1
        if arity == 1:
            output_lines.append(f"export type {name}<T> = T;")
            continue
        params = ", ".join(f"T{index}" for index in range(1, arity + 1))
        output_lines.append(f"export type {name}<{params}> = T1;")

    output_lines.append("")
    output_lines.append("")
    return output_lines


def emit_body_param_interfaces_section(generator_state: GeneratorState) -> list[str]:
    """Emit request body parameter interfaces."""
    output_lines: list[str] = []
    for export_name, spec in sorted(generator_state.body_parameter_interfaces.items(), key=lambda item: item[0]):
        output_lines.extend(emit_parameter_interface_spec(generator_state, spec))
    return output_lines


def emit_query_param_interfaces_section(generator_state: GeneratorState) -> list[str]:
    """Emit query parameter interfaces."""
    output_lines: list[str] = []
    for export_name, spec in sorted(generator_state.query_parameter_interfaces.items(), key=lambda item: item[0]):
        output_lines.extend(emit_parameter_interface_spec(generator_state, spec))
    return output_lines


# ============================================================
# Generic endpoint-keyed maps (static priority + dynamic generics)
# ============================================================

def emit_generic_endpoint_spec_maps(generator_state: GeneratorState) -> list[str]:
    """
    Generates a scalable TS shape that supports:
      - static endpoints taking priority over dynamic matches
      - multiple dynamic endpoints without giant conditional chains
      - different mappings per endpoint for: response/body/query/path
      - collision detection for dynamic template shapes

    Output:
      - EndpointKey
      - Endpoints
      - EndpointParams
      - EndpointQueryParams
      - EndpointPathParams
    """
    discovered_endpoint_keys = list(generator_state.discovered_endpoint_keys)

    static_endpoint_keys = [endpoint_key for endpoint_key in discovered_endpoint_keys if not is_dynamic_endpoint_key(endpoint_key)]
    dynamic_endpoint_keys = [endpoint_key for endpoint_key in discovered_endpoint_keys if is_dynamic_endpoint_key(endpoint_key)]

    # Hard fail if dynamic routes collide by shape (template literal key)
    template_key_to_original_key = build_dynamic_template_index(
        dynamic_endpoint_keys=dynamic_endpoint_keys,
        endpoint_source_files_by_key=generator_state.endpoint_source_files_by_key,
    )

    def typescript_body_type_for(endpoint_key: str) -> str:
        """Resolve the TypeScript body type for an endpoint key."""
        mapped_type = generator_state.endpoint_body_types.get(endpoint_key)
        if mapped_type is not None:
            return mapped_type
        return "never" if generator_state.config.include_never_for_non_body else "unknown"

    def typescript_query_type_for(endpoint_key: str) -> str:
        """Resolve the TypeScript query type for an endpoint key."""
        if not generator_state.config.emit_query_params:
            return "never"
        return generator_state.endpoint_query_types.get(endpoint_key, "never")

    def typescript_path_type_for(endpoint_key: str) -> str:
        """Resolve the TypeScript path params type for an endpoint key."""
        if not generator_state.config.emit_path_params:
            return "never"
        variable_names = generator_state.endpoint_path_variables.get(endpoint_key)
        if not variable_names:
            return "never"
        fields_literal = "; ".join(f"{variable_name}: string" for variable_name in variable_names)
        return f"{{ {fields_literal} }}"

    def dynamic_sort_key(endpoint_key: str) -> tuple[int, int, str]:
        """Sort key to prioritize more specific dynamic routes."""
        # IMPORTANT: more variables first to reduce overlap issues.
        variable_count = len(extract_path_variables(endpoint_key))
        return (-variable_count, -len(endpoint_key), endpoint_key)

    output_lines: list[str] = []

    # ---- StaticEndpointSpec
    output_lines.append("type StaticEndpointSpec = {")
    for endpoint_key in sorted(static_endpoint_keys):
        response_type = generator_state.endpoint_response_types.get(endpoint_key, "unknown")
        body_type = typescript_body_type_for(endpoint_key)
        query_type = typescript_query_type_for(endpoint_key)
        path_type = typescript_path_type_for(endpoint_key)
        output_lines.append(
            f'  "{endpoint_key}": {{ response: {response_type}; body: {body_type}; query: {query_type}; path: {path_type} }};'
        )
    output_lines.append("}")
    output_lines.append("")
    output_lines.append("")

    # ---- DynamicEndpointCases (tuple)
    output_lines.append("type DynamicEndpointCases = [")
    for endpoint_key in sorted(dynamic_endpoint_keys, key=dynamic_sort_key):
        template_literal_key = endpoint_key_to_template_literal_key(endpoint_key)
        # template_literal_key is guaranteed unique due to build_dynamic_template_index()
        # but we still compute it directly for emission (clarity).

        response_type = generator_state.endpoint_response_types.get(endpoint_key, "unknown")
        body_type = typescript_body_type_for(endpoint_key)
        query_type = typescript_query_type_for(endpoint_key)
        path_type = typescript_path_type_for(endpoint_key)

        output_lines.append(
            f"  {{ pattern: {template_literal_key}; response: {response_type}; body: {body_type}; query: {query_type}; path: {path_type} }},"
        )
    output_lines.append("]")
    output_lines.append("")
    output_lines.append("")

    # ---- Generic resolver (static priority, then first dynamic match)
    output_lines.append("type DefaultEndpointSpec = { response: unknown; body: never; query: never; path: never };")
    output_lines.append("")
    output_lines.append("type MatchDynamicSpec<Key extends string, Cases extends readonly unknown[]> =")
    output_lines.append("  Cases extends readonly [infer Head, ...infer Tail extends readonly unknown[]]")
    output_lines.append("    ? Head extends { pattern: infer Pattern }")
    output_lines.append("      ? Pattern extends string")
    output_lines.append("        ? Key extends Pattern")
    output_lines.append("          ? Head")
    output_lines.append("          : MatchDynamicSpec<Key, Tail>")
    output_lines.append("        : DefaultEndpointSpec")
    output_lines.append("      : DefaultEndpointSpec")
    output_lines.append("    : DefaultEndpointSpec;")
    output_lines.append("")
    output_lines.append("")

    output_lines.append("export type EndpointKey = keyof StaticEndpointSpec | DynamicEndpointCases[number]['pattern'];")
    output_lines.append("")
    output_lines.append("type EndpointSpecFor<Key extends EndpointKey> =")
    output_lines.append("  Key extends keyof StaticEndpointSpec")
    output_lines.append("    ? StaticEndpointSpec[Key]")
    output_lines.append("    : MatchDynamicSpec<Key, DynamicEndpointCases>;")
    output_lines.append("")
    output_lines.append("")

    output_lines.append("export type Endpoints = { [Key in EndpointKey]: EndpointSpecFor<Key>['response'] };")
    output_lines.append("export type EndpointParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['body'] };")
    output_lines.append("export type EndpointQueryParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['query'] };")
    output_lines.append("export type EndpointPathParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['path'] };")
    output_lines.append("")
    output_lines.append("")

    output_lines.append("export type EndpointSpec<K extends EndpointKey> = EndpointSpecFor<K>;")
    output_lines.append('export type EndpointResponse<K extends EndpointKey> = EndpointSpecFor<K>["response"];')
    output_lines.append('export type EndpointBody<K extends EndpointKey> = EndpointSpecFor<K>["body"];')
    output_lines.append('export type EndpointQuery<K extends EndpointKey> = EndpointSpecFor<K>["query"];')
    output_lines.append('export type EndpointPath<K extends EndpointKey> = EndpointSpecFor<K>["path"];')
    output_lines.append("")
    output_lines.append("")


    # Keep this around as an internal sanity reference (not emitted), so you can debug collisions quickly.
    _ = template_key_to_original_key

    return output_lines


def emit_tsunami_module_augmentation(generator_state: GeneratorState) -> list[str]:
    """Augment tsunami EndpointSpecMap with generated endpoint specs."""
    return [
        "type __TsunamiEndpointSpecMap = { [K in EndpointKey]: EndpointSpec<K> };",
        "",
        'declare module "tsunami" {',
        "  interface EndpointSpecMap extends __TsunamiEndpointSpecMap {}",
        "}",
        "",
        "",
    ]


# ============================================================
# Example future decorator: @authorized("admin") / @authorized(role="admin")
# ============================================================

def transform_collect_authorized_method_decorator(
    decorator_instance: DecoratorInstance,
    endpoint_metadata: EndpointMetadata,
    generator_state: GeneratorState,
) -> None:
    """Collect optional authorization role metadata from decorators."""
    role_expression: ast.expr | None = None

    if decorator_instance.positional_args:
        role_expression = decorator_instance.positional_args[0]
    elif "role" in decorator_instance.keyword_args:
        role_expression = decorator_instance.keyword_args["role"]

    role_value = "unknown"
    if isinstance(role_expression, ast.Constant) and isinstance(role_expression.value, str):
        role_value = role_expression.value

    generator_state.endpoint_authorization_roles[endpoint_metadata.endpoint_key] = role_value


# ============================================================
# Default registry preset (main stays stable)
# ============================================================

def create_default_registry(config: TypeScriptGeneratorConfig) -> TransformerRegistry:
    """Build the default registry of transformers and emitters."""
    registry = TransformerRegistry()

    # Decorator-driven collection (registry controlled)
    registry.add_method_decorator(config.query_params_decorator_name, transform_collect_endpoint_query_params_from_decorator)

    # Method-level collection (registry controlled)
    registry.add_method(transform_set_query_params_default_never)
    registry.add_method(transform_collect_endpoint_body_params_from_signature)
    registry.add_method(transform_collect_endpoint_response_types)
    registry.add_method(transform_collect_endpoint_path_variables)

    # Emit blocks
    registry.add_method(emit_imports_section)
    registry.add_method(emit_referenced_dataclasses_section)
    registry.add_method(emit_response_wrappers_section)
    registry.add_method(emit_referenced_aliases_section)
    registry.add_method(emit_body_param_interfaces_section)
    registry.add_method(emit_query_param_interfaces_section)
    registry.add_method(emit_passthrough_generic_types_section)

    # Generic key-based maps (static wins over dynamic)
    registry.add_method(emit_generic_endpoint_spec_maps)
    registry.add_method(emit_tsunami_module_augmentation)

    return registry


# ============================================================
# CLI
# ============================================================

def parse_allowed_methods(raw_value: str | None) -> set[str] | None:
    """Parse a comma-separated list of HTTP methods from CLI input."""
    if not raw_value:
        return None
    parts = {part.strip() for part in raw_value.split(",") if part.strip()}
    return parts or None


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for generating TypeScript types."""
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("inputs", nargs="+", help="Python files, globs, or directories")
    argument_parser.add_argument("--class", dest="route_class", default="Endpoint")
    argument_parser.add_argument(
        "--out",
        dest="out",
        default=None,
        help="Write to file instead of stdout (default: template/library/api.types.ts if present).",
    )

    argument_parser.add_argument(
        "--allowed-methods",
        dest="allowed_methods",
        default=None,
        help="Comma-separated allowlist. Example: --allowed-methods get,post,put,patch (default: all)",
    )
    argument_parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=None,
        help="Max number of methods per file (after sorting by name).",
    )
    argument_parser.add_argument(
        "--index-as",
        dest="index_as",
        default=None,
        help='Treat index() as this method name when building keys. Example: --index-as get',
    )

    argument_parser.add_argument(
        "--contracts-out",
        dest="contracts_out",
        default=None,
        help="Write api.contracts.ts (re-export file). Default: alongside --out if provided.",
    )

    argument_parser.add_argument(
        "--contracts-import",
        dest="contracts_import",
        default=None,
        help='Import path used inside contracts file (default: auto-relative to types file, ex: "./api.types").',
    )


    parsed_args = argument_parser.parse_args(argv)
    if parsed_args.out is None:
        default_out_path = Path("template/library/api.types.ts")
        if default_out_path.parent.is_dir():
            parsed_args.out = str(default_out_path)

    type_mapping_overrides, generic_type_overrides = load_type_mapping(DEFAULT_TYPE_MAP_PATH)
    base_primitive_type_map = TypeScriptGeneratorConfig().primitive_type_map

    config = TypeScriptGeneratorConfig(
        route_class_name=parsed_args.route_class,
        index_method_alias=parsed_args.index_as,
        primitive_type_map={**base_primitive_type_map, **type_mapping_overrides},
        generic_type_map=generic_type_overrides,
    )

    registry = create_default_registry(config)

    # Future extension example:
    # registry.add_method_decorator("authorized", transform_collect_authorized_method_decorator)

    generated_typescript = Pipeline.run(
        registry,
        inputs=parsed_args.inputs,
        config=config,
        allowed_methods=parse_allowed_methods(parsed_args.allowed_methods),
        per_file_limit=parsed_args.limit,
    )

    if parsed_args.out:
        output_path = Path(parsed_args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated_typescript, encoding="utf-8")
    else:
        print(generated_typescript, end="")

    generator_state = Pipeline.build_state(
        registry,
        inputs=parsed_args.inputs,
        config=config,
        allowed_methods=parse_allowed_methods(parsed_args.allowed_methods),
        per_file_limit=parsed_args.limit,
    )

    generated_typescript = Pipeline.emit_typescript(registry, generator_state)

    types_out_path: Path | None = None
    if parsed_args.out:
        types_out_path = Path(parsed_args.out)
        types_out_path.parent.mkdir(parents=True, exist_ok=True)
        types_out_path.write_text(generated_typescript, encoding="utf-8")
    else:
        print(generated_typescript, end="")

    # ---- contracts output ----
    contracts_out_path: Path | None = None

    if parsed_args.contracts_out:
        contracts_out_path = Path(parsed_args.contracts_out)
    elif types_out_path is not None:
        # Default: api.types.ts -> api.contracts.ts
        if types_out_path.name.endswith(".types.ts"):
            contracts_out_path = types_out_path.with_name(types_out_path.name.replace(".types.ts", ".contracts.ts"))
        else:
            contracts_out_path = types_out_path.with_name(f"{types_out_path.stem}.contracts.ts")

    if contracts_out_path is not None:
        contracts_out_path.parent.mkdir(parents=True, exist_ok=True)

        if parsed_args.contracts_import:
            types_module_path = ensure_relative_typescript_import_path(parsed_args.contracts_import)
        elif types_out_path is not None:
            types_module_path = compute_typescript_import_path_without_extension(
                from_file=contracts_out_path,
                to_file=types_out_path,
            )
        else:
            # If you're printing types to stdout, we can't reliably auto-compute.
            types_module_path = "./api.types"

        contracts_typescript = render_contracts_typescript_file(
            generator_state,
            types_module_path=types_module_path,
        )
        contracts_out_path.write_text(contracts_typescript, encoding="utf-8")


    return 0


if __name__ == "__main__":
    raise SystemExit(main())
