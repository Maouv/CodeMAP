"""Core AST traversal — Layer 1 static analysis (BLUEPRINT Section 4)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


# --- Data carriers (shape finalized by graph_builder.py) ---------------------

@dataclass
class ParsedFunction:
    name: str
    qualified_name: str          # module.Class.method or module.func
    lineno: int
    is_nested: bool = False      # Section 14: nested funcs are children, not top-level
    is_property: bool = False    # Section 14: @property flag
    decorators: list[str] = field(default_factory=list)
    parent: str | None = None    # enclosing func/class qualified_name


@dataclass
class ParsedImport:
    target: str
    lineno: int
    is_conditional: bool = False  # Section 14: try/except import
    is_star: bool = False         # Section 14: from X import * (weight -1)
    is_dynamic: bool = False      # Section 14: importlib → warning, no edge


@dataclass
class ParseResult:
    path: Path
    functions: list[ParsedFunction] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    exported_names: list[str] = field(default_factory=list)  # __all__ override
    warnings: list[str] = field(default_factory=list)


# --- Pre-parse guards (Section 14 edge cases) --------------------------------

def safe_parse(path: Path) -> ParseResult:
    """Guarded entry point: size/timeout/encoding checks, then run visitor.

    Section 14 guards before ast.parse():
      - file > 1MB        → skip + warning
      - parse timeout >5s → skip + warning
      - non-UTF-8         → tokenize.detect_encoding()
    Returns ParseResult with warnings populated; never raises on bad input.
    """
    ...


# --- Visitor (stdlib ast.NodeVisitor dispatch) -------------------------------

class _ScannerVisitor(ast.NodeVisitor):
    """Single-pass visitor. Tracks scope stack for nesting/qualified names."""

    def __init__(self, module_name: str) -> None:
        ...

    # Section 14: nested funcs → is_nested via scope stack
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None: ...
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None: ...

    def visit_ClassDef(self, node: ast.ClassDef) -> None: ...

    # Section 14: plain + star imports
    def visit_Import(self, node: ast.Import) -> None: ...
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None: ...

    # Section 14: __all__ → exported_names; importlib/exec/eval → warnings
    def visit_Assign(self, node: ast.Assign) -> None: ...
    def visit_Call(self, node: ast.Call) -> None: ...

    # Section 14: try/except import → is_conditional on both branches
    def visit_Try(self, node: ast.Try) -> None: ...

    def result(self) -> ParseResult: ...


def _decorator_name(node: ast.expr) -> str:
    """Flatten a decorator expr to dotted string (detect @property)."""
    ...
