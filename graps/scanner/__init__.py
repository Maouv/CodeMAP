"""Scanner public interface — BLUEPRINT §4 (BaseParser Interface).

Defines the data carriers (ParsedFile / ParsedFunction / ParsedImport) and the
BaseParser Protocol every parser implements (ASTParser now, TreeSitterParser in
Phase 4). graph_builder and layers above import ONLY from here — never from a
concrete parser module — so Phase 4 tree-sitter does not cascade.

ponytail: BLUEPRINT §4 field set is present verbatim; legacy Phase 1 fields that
tests/graph_builder/risk_analyzer/resolver read are preserved with defaults +
comments (one set of dataclasses, not two — deletion over addition).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class ParsedFunction:
    name: str
    # --- BLUEPRINT §4 fields (parser MVP fills name/decorators/line_start; rest
    #     default until Phase 2/4 extraction) ---
    params: list[dict[str, object]] = field(default_factory=list)
    returns: str | None = None
    line_start: int = 0
    line_end: int = 0
    decorators: list[str] = field(default_factory=list)
    is_private: bool = False
    callers: list[str] = field(default_factory=list)   # filled by graph_builder, not parser
    callees: list[dict[str, object]] = field(default_factory=list)
    # --- ponytail: legacy Phase 1 fields; tests + graph_builder/risk_analyzer read them ---
    qualified_name: str = ""
    lineno: int = 0
    is_nested: bool = False      # Section 14: nested funcs are children, not top-level
    is_property: bool = False    # Section 14: @property flag
    parent: str | None = None    # enclosing func/class qualified_name


@dataclass
class ParsedImport:
    """ponytail: not in BLUEPRINT §4 — preserved (resolver/risk_analyzer/tests read its fields)."""
    target: str
    lineno: int = 0
    is_conditional: bool = False  # Section 14: try/except import
    is_star: bool = False         # Section 14: from X import * (weight -1)
    is_dynamic: bool = False      # Section 14: importlib → warning, no edge


@dataclass
class ParsedFile:
    # --- BLUEPRINT §4 fields ---
    id: str = ""                                   # relative path from scan root
    # ponytail: BLUEPRINT §4 says path:str (relative); actual parser stores the
    # absolute Path here (resolver uses .parent, graph_builder._rel wraps in Path).
    # `id` carries the BLUEPRINT relative-path semantic. Preserve until Phase 4 rewrite.
    path: Path = field(default_factory=lambda: Path(""))
    functions: list[ParsedFunction] = field(default_factory=list)
    # ponytail: BLUEPRINT §4 says imports:list[dict]; ParsedImport preserved because
    # resolver/risk_analyzer/tests read .target/.is_star/.is_dynamic/.is_conditional.
    imports: list[ParsedImport] = field(default_factory=list)
    constants: list[dict[str, object]] = field(default_factory=list)
    classes: list[dict[str, object]] = field(default_factory=list)
    exported_names: list[str] = field(default_factory=list)
    file_modified_at: str = ""
    language: str = "python"
    # --- ponytail: preserved from Phase 1; graph_builder/risk_analyzer iterate warnings ---
    warnings: list[str] = field(default_factory=list)


# ponytail: legacy alias so risk_analyzer (`from .ast_parser import ParseResult`)
# keeps working untouched. Canonical name is ParsedFile (BLUEPRINT §4).
ParseResult = ParsedFile


@runtime_checkable
class BaseParser(Protocol):
    def parse_file(self, path: Path, root: Path) -> ParsedFile | None: ...
    def supported_extensions(self) -> list[str]: ...

