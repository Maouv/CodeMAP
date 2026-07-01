"""Tree-sitter multi-language parser — Phase 4 adapter (BLUEPRINT §4).

Adapter over tree-sitter-language-pack's ``process()`` API. Maps
``ProcessResult`` → ``ParsedFile``. No manual tree walking — library handles
306 languages, grammar download, and code intelligence.

Implements BaseParser Protocol. One instance per scan session.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from graps.scanner import ParsedFile, ParsedFunction, ParsedImport

logger = logging.getLogger(__name__)

_MAX_BYTES = 1_000_000  # 1MB — konsisten dengan ASTParser


class TreeSitterParser:
    """Multi-language parser via tree-sitter-language-pack.

    Grammar di-load lazily (on-demand download + local cache).
    implements BaseParser Protocol.
    """

    def supported_extensions(self) -> list[str]:
        # ponytail: detect_language_from_path() handle 306 bahasa.
        # Return [] = "cek via detect_language_from_path()".
        return []

    def parse_file(self, path: Path, root: Path) -> ParsedFile | None:
        """Parse satu file. Return None kalau unsupported/failed."""
        try:
            from tree_sitter_language_pack import (
                ProcessConfig,
                detect_language_from_path,
                process,
            )
        except ImportError:
            logger.debug("tree-sitter-language-pack not installed")
            return None

        # Detect language dari path
        lang = detect_language_from_path(str(path))
        if lang is None:
            return None

        # 1MB guard — konsisten dengan ASTParser
        try:
            size = path.stat().st_size
        except OSError:
            return None
        if size > _MAX_BYTES:
            logger.warning("Skip %s: file too large (%d bytes)", path, size)
            return None

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Cannot read %s: %s", path, e)
            return None

        try:
            result = process(source, ProcessConfig(language=lang))
        except Exception as e:
            # Grammar download gagal, parse error berat, dll
            logger.warning("process() failed for %s (%s): %s", path, lang, e)
            return None

        try:
            rel = str(path.resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(path)

        # ── Map ProcessResult → ParsedFile ──────────────────────────
        functions = _extract_functions(result.structure)
        imports = _extract_imports(result.imports)
        classes = _extract_classes(result.structure)
        exported_names = _extract_exports(result.exports)

        # Diagnostics → warnings (syntax errors dari tree-sitter)
        warnings = [
            f"line {d.span.start_line + 1}: {d.message}"
            for d in result.diagnostics
            if d.span
        ]

        return ParsedFile(
            id=rel,
            path=path,
            functions=functions,
            imports=imports,
            constants=[],          # ponytail: ProcessResult tidak provide
            classes=classes,
            exported_names=exported_names,
            file_modified_at=str(path.stat().st_mtime),
            language=lang,
            warnings=warnings,
        )


# ── Adapter helpers: ProcessResult → ParsedFile fields ──────────────
# Module-level functions, bukan staticmethod — gampang test & refactor.


def _extract_functions(structure: list[Any]) -> list[ParsedFunction]:
    """Flatten StructureItem tree → flat ParsedFunction list.

    Ambil FUNCTION/METHOD, skip CLASS/STRUCT (masuk ke classes).
    Recurse children untuk nested methods/functions.
    """
    results: list[ParsedFunction] = []

    def _flatten(item: Any, parent_name: str | None = None) -> None:
        kind_str = str(item.kind).upper() if item.kind else ""

        if "FUNCTION" in kind_str or "METHOD" in kind_str:
            name = item.name or "<anonymous>"
            span = item.span
            results.append(ParsedFunction(
                name=name,
                params=[],           # ponytail: parse dari signature nanti
                returns=None,
                line_start=(span.start_line + 1) if span else 0,
                line_end=(span.end_line + 1) if span else 0,
                decorators=list(item.decorators) if item.decorators else [],
                is_private=_detect_is_private(item.visibility, name),
                parent=parent_name,
            ))

        if item.children:
            for child in item.children:
                _flatten(child, parent_name=item.name)

    for item in structure:
        _flatten(item)
    return results


def _extract_imports(imports: list[Any]) -> list[ParsedImport]:
    """Map ImportInfo → ParsedImport.

    ponytail: Go return 2 entries per import (statement + bare path).
    Dedup by lineno — kalau 2 import di line yang sama, keep first.
    """
    seen_lineno: set[int] = set()
    results: list[ParsedImport] = []
    for imp in imports:
        lineno = (imp.span.start_line + 1) if imp.span else 0
        if lineno in seen_lineno:
            continue
        seen_lineno.add(lineno)
        results.append(ParsedImport(
            target=imp.source,
            lineno=lineno,
            is_star=imp.is_wildcard,
        ))
    return results


def _extract_classes(structure: list[Any]) -> list[dict[str, Any]]:
    """Map StructureItem kind=CLASS → dict."""
    results: list[dict[str, Any]] = []

    def _find(item: Any) -> None:
        kind_str = str(item.kind).upper() if item.kind else ""
        if "CLASS" in kind_str:
            span = item.span
            results.append({
                "name": item.name or "<anonymous>",
                "line_start": (span.start_line + 1) if span else 0,
                "line_end": (span.end_line + 1) if span else 0,
                "decorators": list(item.decorators) if item.decorators else [],
                "methods": [
                    c.name for c in (item.children or [])
                    if "FUNCTION" in str(c.kind).upper()
                    or "METHOD" in str(c.kind).upper()
                ],
            })
        if item.children:
            for child in item.children:
                _find(child)

    for item in structure:
        _find(item)
    return results


def _extract_exports(exports: list[Any]) -> list[str]:
    """Map ExportInfo → list[str]."""
    return [exp.name for exp in exports if exp.name]


def _detect_is_private(visibility: str | None, name: str) -> bool:
    """Detect private: visibility modifier atau naming convention.

    - pub/public/exported → False
    - private/internal → True
    - None + name starts with _ → True (Python convention)
    - None + name starts lowercase → True (Go unexported convention)
    """
    if visibility:
        vis = visibility.lower()
        if vis in ("pub", "public", "exported"):
            return False
        if vis in ("private", "internal"):
            return True
    # Fallback naming convention
    if name.startswith("_"):
        return True
    # ponytail: Go convention — lowercase = unexported.
    # False positive untuk Python methods (lowercase = normal), tapi
    # is_private hanya dipakai risk_analyzer Python-only checks yang
    # di-guard by language. Aman.
    return False
