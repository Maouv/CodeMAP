"""Convergence point — assemble scanner outputs into the graph JSON (BLUEPRINT §7).

Phase 1: builds only what the parser actually produces. Schema fields with no
upstream data yet are filled with schema-shaped defaults and a ponytail comment.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from graps.scanner import ParsedFile, ParsedImport

from .resolver import resolve_import
from .risk_analyzer import analyze_risks
from .sanitize import sanitize_constant_value

# ponytail: memoize resolve_import per build_graph call; O(k) → 2× O(k) fs I/O.
# Cache keyed by (target, is_dynamic, is_star, current_file, root) — ParsedImport
# isn't hashable (dataclass default), so we extract fields.
_resolve_cache: dict[tuple[str, bool, bool, Path, Path], Path | None] = {}

def _resolved(imp: ParsedImport, current_file: Path, root: Path) -> Path | None:
    key = (imp.target, imp.is_dynamic, imp.is_star, current_file, root)
    if key not in _resolve_cache:
        _resolve_cache[key] = resolve_import(imp, current_file, root)
    return _resolve_cache[key]


def _rel(path: Path, root: Path) -> str:
    """Path relative to root as str (M-03: never leak absolute paths)."""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)  # already relative / outside root


def _sanitized_constants(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run every constant value through sanitize_constant_value (C-01).

    ponytail: Phase 2 extracts module constants in the parser; sanitize is
    already wired here so C-01 cannot be bypassed once data arrives.
    """
    return [
        {"name": c["name"],
         "value": sanitize_constant_value(c["name"], c["value"]),
         "line": c.get("line")}
        for c in raw
    ]


def _warning_type(msg: str) -> str:
    """Lazy keyword map from parser warning string to §7 warning type."""
    m = msg.lower()
    if "star import" in m:
        return "star_import"
    if "importlib" in m or "dynamic import" in m:
        return "dynamic_import"
    if "dynamic_code" in m:
        return "dynamic_code"
    return "scan_warning"


def _build_node(result: ParsedFile, all_results: list[ParsedFile], root: Path) -> dict[str, Any]:
    rel = _rel(result.path, root)
    risks = analyze_risks(result, all_results)

    functions = [{
        "name": f.name,
        "type": "function",
        "decorators": f.decorators,
        "is_private": f.name.startswith("_"),
        "line_start": f.lineno,
        # ponytail: Phase 2 fields — no parser data yet, schema-shaped defaults.
        "params": [],
        "returns": None,
        "line_end": None,
        "criticality": None,
        "callers": [],
        "callees": [],
        "is_dead_code": False,
        "risks": [],
        "ai_summary": None,
    } for f in result.functions]

    imports = [{
        "from": imp.target,
        "resolved_path": (lambda r: _rel(r, root) if r else None)(
            _resolved(imp, result.path, root)),
        "is_dynamic": imp.is_dynamic,
        "is_star": imp.is_star,
        "is_conditional": imp.is_conditional,
    } for imp in result.imports]

    return {
        "id": rel,
        "type": "file",
        "path": rel,
        "risk_level": None,        # ponytail: Phase 2 risk rollup
        "risk_summary": None,      # ponytail: Phase 2 risk rollup
        "functions": functions,
        "classes": [],             # ponytail: Phase 2 class extraction in parser
        "imports": imports,
        "constants": _sanitized_constants(result.constants),  # C-01: parser constants → sanitize → graph
        "has_all_definition": bool(result.exported_names),
        "exported_names": result.exported_names,
        "file_modified_at": None,  # ponytail: passed from CLI stat() in a later phase
        "risks": risks,            # file-level risks (Phase 1: star_import)
    }


def _build_edges(results: list[ParsedFile], root: Path) -> list[dict[str, Any]]:
    """One edge per (source, resolved target). weight = #import names to target."""
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for result in results:
        src = _rel(result.path, root)
        for imp in result.imports:
            if imp.is_dynamic or imp.is_star:
                continue
            target = _resolved(imp, result.path, root)
            if target is None:  # stdlib / 3rd-party / unresolved
                continue
            tgt = _rel(target, root)
            edge = edges.setdefault((src, tgt), {
                "source": src, "target": tgt, "type": "imports",
                "weight": 0, "imported_names": [],
            })
            edge["weight"] += 1
            edge["imported_names"].append(imp.target)
    return list(edges.values())


def build_graph(results: list[ParsedFile], root: Path) -> dict[str, Any]:
    edges = _build_edges(results, root)
    nodes = [_build_node(r, results, root) for r in results]

    warnings: list[dict[str, Any]] = []
    for result in results:
        rel = _rel(result.path, root)
        for w in result.warnings:
            warnings.append({"type": _warning_type(w), "file": rel, "detail": w})

    total_functions = sum(len(r.functions) for r in results)
    meta = {
        "root": _rel(root, root),
        "scanned_at": datetime.now().isoformat(),
        "total_files": len(results),
        "total_functions": total_functions,
        "total_edges": len(edges),
        "has_warnings": bool(warnings),
    }
    return {"meta": meta, "nodes": nodes, "edges": edges, "warnings": warnings}


if __name__ == "__main__":
    # ponytail: self-check builds synthetic ParsedFile objects — no parser import —
    # so graph_builder stays parser-agnostic (BLUEPRINT §4). Fixtures integration
    # lives in tests/test_graph_builder.py.
    import tempfile

    from graps.scanner import ParsedFile, ParsedFunction, ParsedImport

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        star = ParsedFile(
            id="star.py", path=root / "star.py",
            imports=[ParsedImport(target="os", lineno=1, is_star=True)],
            warnings=["line 1: star import from 'os'"],
        )
        svc = ParsedFile(
            id="svc.py", path=root / "svc.py",
            functions=[ParsedFunction(name="hello", lineno=2)],
        )
        # Finding 1 regression: constants must flow parser → build_graph → C-01 sanitize.
        cfg = ParsedFile(
            id="cfg.py", path=root / "cfg.py",
            constants=[{"name": "MAX_RETRY", "value": "3", "line": 1},
                       {"name": "DB_PASSWORD", "value": "hunter2", "line": 2}],
        )
        graph = build_graph([star, svc, cfg], root)

        assert set(graph) == {"meta", "nodes", "edges", "warnings"}, graph.keys()
        assert graph["meta"]["total_files"] == 3
        # star_import → warning (resolver gives star imports no edge, §7).
        assert any(w["type"] == "star_import" for w in graph["warnings"]), graph["warnings"]
        # C-01 wiring proof through the real build_graph path (not the helper in isolation).
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["cfg.py"]["constants"] == [
            {"name": "MAX_RETRY", "value": "3", "line": 1},
            {"name": "DB_PASSWORD", "value": "[REDACTED]", "line": 2},
        ], nodes["cfg.py"]["constants"]
        # files without parser constants stay empty.
        assert nodes["star.py"]["constants"] == [] and nodes["svc.py"]["constants"] == []

    print("self-check ok")
