"""Core AST traversal — Layer 1 static analysis (BLUEPRINT Section 4)."""

from __future__ import annotations

import ast
import signal
import tokenize
from pathlib import Path

from graps.scanner import ParsedFile, ParsedFunction, ParsedImport, ParseResult

_MAX_BYTES = 1_000_000  # 1MB (Section 14)
_TIMEOUT_S = 5          # Section 14

# ponytail: re-export data carriers + legacy ParseResult alias so resolver/
# risk_analyzer keep importing from this module untouched. BLUEPRINT §4 only
# forbids graph_builder+above from importing the concrete *parser*; data
# carriers may be re-exported.
__all__ = [
    "safe_parse", "ASTParser",
    "ParsedFile", "ParsedFunction", "ParsedImport", "ParseResult",
]


# Data carriers now live in graps.scanner (BLUEPRINT §4 BaseParser interface).
# --- Pre-parse guards (Section 14 edge cases) --------------------------------

def safe_parse(path: Path) -> ParsedFile:
    """Guarded entry point: size/timeout/encoding checks, then run visitor.

    Section 14 guards before ast.parse():
      - file > 1MB        → skip + warning
      - parse timeout >5s → skip + warning
      - non-UTF-8         → tokenize.detect_encoding()
    Returns ParsedFile with warnings populated; never raises on bad input.
    """
    result = ParsedFile(path=path)

    try:
        if path.stat().st_size > _MAX_BYTES:
            result.warnings.append(f"{path}: file too large (>1MB), skipped")
            return result
    except OSError as e:
        result.warnings.append(f"{path}: stat failed: {e}")
        return result

    # Detect encoding from the file's coding cookie before reading (Section 14).
    try:
        with open(path, "rb") as fb:
            encoding, _ = tokenize.detect_encoding(fb.readline)
        source = path.read_text(encoding=encoding)
    except (OSError, SyntaxError, UnicodeDecodeError, LookupError) as e:
        result.warnings.append(f"{path}: encoding/read error: {e}")
        return result

    # ponytail: signal.alarm is Unix-only; non-Unix runs without a timeout guard.
    has_alarm = hasattr(signal, "SIGALRM")

    def _timeout(signum, frame):
        raise TimeoutError

    if has_alarm:
        old = signal.signal(signal.SIGALRM, _timeout)
        signal.alarm(_TIMEOUT_S)
    try:
        tree = ast.parse(source, filename=str(path))
    except (TimeoutError, SyntaxError, MemoryError, ValueError, RecursionError) as e:
        result.warnings.append(f"{path}: parse failed: {type(e).__name__}: {e}")
        return result
    finally:
        if has_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    visitor = _ScannerVisitor(path.stem)
    visitor.visit(tree)
    parsed = visitor.result()
    parsed.path = path
    parsed.warnings = result.warnings + parsed.warnings
    return parsed


class ASTParser:
    """Python stdlib ``ast`` parser implementing BaseParser (BLUEPRINT §4).

    Adapter over module-level :func:`safe_parse`: keeps the proven guarded parse
    path while exposing the Protocol shape Phase 4 cli dispatch needs. Always
    returns a ParsedFile (warnings populated on failure); the ``| None`` in the
    Protocol is reserved for future parsers that skip unsupported files.
    """

    def parse_file(self, path: Path, root: Path) -> ParsedFile | None:
        pf = safe_parse(path)
        # ponytail: id = path relative to root (BLUEPRINT §4); mirrors graph_builder._rel.
        try:
            pf.id = str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            pf.id = str(path)
        return pf

    def supported_extensions(self) -> list[str]:
        return [".py"]


# --- Visitor (stdlib ast.NodeVisitor dispatch) -------------------------------

class _ScannerVisitor(ast.NodeVisitor):
    """Single-pass visitor. Tracks scope stack for nesting/qualified names."""

    def __init__(self, module_name: str) -> None:
        self.module = module_name
        self._scope: list[str] = [module_name]      # qualified-name components
        self._kind: list[str] = ["module"]           # parallel: module/class/func
        self._in_try = 0                             # try-body depth (Section 14)
        self.functions: list[ParsedFunction] = []
        self.imports: list[ParsedImport] = []
        self.exported_names: list[str] = []
        self.warnings: list[str] = []

    def _qual(self, name: str) -> str:
        return ".".join(self._scope + [name])

    def _handle_func(self, node) -> None:
        is_nested = "func" in self._kind  # an enclosing function exists
        self.functions.append(ParsedFunction(
            name=node.name,
            qualified_name=self._qual(node.name),
            lineno=node.lineno,
            is_nested=is_nested,
            is_property=any(_decorator_name(d) == "property" for d in node.decorator_list),
            decorators=[_decorator_name(d) for d in node.decorator_list],
            parent=".".join(self._scope) if self._kind[-1] != "module" else None,
        ))
        self._scope.append(node.name)
        self._kind.append("func")
        self.generic_visit(node)
        self._scope.pop()
        self._kind.pop()

    # Section 14: nested funcs → is_nested via scope stack
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_func(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self._kind.append("class")
        self.generic_visit(node)
        self._scope.pop()
        self._kind.pop()

    # Section 14: plain + star imports
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ParsedImport(
                target=alias.name, lineno=node.lineno,
                is_conditional=bool(self._in_try),
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = "." * (node.level or 0) + (node.module or "")
        sep = "" if base.endswith(".") else "."  # keep leading dots for relative imports
        for alias in node.names:
            star = alias.name == "*"
            self.imports.append(ParsedImport(
                target=base if star else f"{base}{sep}{alias.name}",
                lineno=node.lineno,
                is_conditional=bool(self._in_try),
                is_star=star,
            ))
            if star:
                self.warnings.append(f"line {node.lineno}: star import from {base!r}")

    # Section 14: __all__ → exported_names; importlib/exec/eval → warnings
    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                self.exported_names = [
                    e.value for e in node.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fn = _decorator_name(node.func)
        if fn in ("exec", "eval"):
            self.warnings.append(f"line {node.lineno}: dynamic_code ({fn})")
        elif fn in ("importlib.import_module", "import_module"):
            self.warnings.append(f"line {node.lineno}: dynamic import (importlib)")
            self.imports.append(ParsedImport(
                target="<dynamic>", lineno=node.lineno,
                is_conditional=bool(self._in_try), is_dynamic=True,
            ))
        self.generic_visit(node)

    # Section 14: try/except import → is_conditional on both branches
    def visit_Try(self, node: ast.Try) -> None:
        self._in_try += 1
        for child in node.body:
            self.visit(child)
        self._in_try -= 1
        for h in node.handlers:
            self._in_try += 1
            for child in h.body:
                self.visit(child)
            self._in_try -= 1
        for child in node.orelse + node.finalbody:
            self.visit(child)

    def result(self) -> ParsedFile:
        return ParsedFile(
            path=Path(self.module),
            functions=self.functions,
            imports=self.imports,
            exported_names=self.exported_names,
            warnings=self.warnings,
        )


def _decorator_name(node: ast.expr) -> str:
    """Flatten a decorator expr to dotted string (detect @property)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_decorator_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):           # @app.route("/") → app.route
        return _decorator_name(node.func)
    return ""


if __name__ == "__main__":
    import tempfile

    src = '''
import os
from a import *
__all__ = ["foo", "Bar"]

class Bar:
    @property
    def p(self): ...
    def m(self):
        def inner(): ...

def foo():
    exec("x=1")

try:
    import fast_json as j
except ImportError:
    import json as j

import importlib
importlib.import_module("dynamic.mod")
'''
    p = Path(tempfile.mkdtemp()) / "sample.py"
    p.write_text(src)
    r = safe_parse(p)

    quals = {f.qualified_name: f for f in r.functions}
    assert "sample.Bar.m.inner" in quals and quals["sample.Bar.m.inner"].is_nested
    assert not quals["sample.foo"].is_nested
    assert quals["sample.Bar.p"].is_property
    assert quals["sample.Bar.m"].parent == "sample.Bar"
    assert quals["sample.foo"].parent is None

    assert r.exported_names == ["foo", "Bar"]
    assert any(i.is_star for i in r.imports)
    assert any(i.is_conditional and i.target == "fast_json" for i in r.imports)
    assert any(i.is_dynamic for i in r.imports)
    assert any("dynamic_code" in w for w in r.warnings)
    assert any("importlib" in w for w in r.warnings)

    # guards: oversized + syntax error never raise
    big = Path(tempfile.mkdtemp()) / "big.py"
    big.write_text("x = 1\n" * 200_000)
    assert "too large" in " ".join(safe_parse(big).warnings)
    bad = Path(tempfile.mkdtemp()) / "bad.py"
    bad.write_text("def (:\n")
    assert "parse failed" in " ".join(safe_parse(bad).warnings)

    print("self-check ok")
