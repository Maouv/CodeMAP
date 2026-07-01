"""Static risk flags — Layer 1 (BLUEPRINT Section 9).

Phase 4: language-aware. ``star_import`` is universal (wildcard import exists
in Python, JS/TS, Go). ``circular_import_toplevel`` is Python-only (uses
cross-file import graph from all_results). Other Phase 2 risks
(none_return, uncaught_exception, type_annotation, unused_parameter, dead_code)
need data parsers don't provide yet — deferred.
"""

from __future__ import annotations

from .ast_parser import ParseResult


def analyze_risks(
    result: ParseResult, all_results: list[ParseResult]
) -> list[dict[str, object]]:
    """Return risk dicts for ``result``. Language-aware via ``result.language``.

    Universal: star_import.
    Python-only: circular_import_toplevel.
    """
    risks: list[dict[str, object]] = []

    # ── Universal: star_import ──────────────────────────────────────
    for imp in result.imports:
        if imp.is_star:
            risks.append({
                "type": "star_import",
                "severity": "medium",  # §9 table
                "detail": f"star import from {imp.target!r} (line {imp.lineno})",
                "affected_files": [str(result.path)],
            })

    # ── Python-only: circular_import_toplevel ───────────────────────
    if result.language == "python":
        risks.extend(_check_circular_imports(result, all_results))

    return risks


def _check_circular_imports(
    result: ParseResult, all_results: list[ParseResult]
) -> list[dict[str, object]]:
    """Detect top-level circular imports (Python-only).

    A → B, B → A where neither import is conditional (try/except = lazy).
    Uses file stem as module-name proxy — simple, works for flat projects.
    """
    # ponytail: stem → ParsedFile map. Doesn't handle __init__.py packages,
    # but covers the common case. Upgrade when needed.
    by_module: dict[str, ParseResult] = {}
    for pf in all_results:
        by_module[pf.path.stem] = pf

    my_stem = result.path.stem
    flags: list[dict[str, object]] = []

    for imp in result.imports:
        if imp.is_conditional or imp.is_dynamic or imp.is_star:
            continue  # conditional = lazy import, not circular

        target = imp.target.split(".")[0]  # "a.b" → "a"
        target_pf = by_module.get(target)
        if target_pf is None or target_pf is result:
            continue  # external/stdlib or self-import

        # Check if target imports us back (non-conditional)
        for back_imp in target_pf.imports:
            if back_imp.is_conditional or back_imp.is_dynamic or back_imp.is_star:
                continue
            back_target = back_imp.target.split(".")[0]
            if back_target == my_stem:
                flags.append({
                    "type": "circular_import_toplevel",
                    "severity": "high",
                    "detail": f"circular import: {my_stem} → {target} → {my_stem}",
                    "affected_files": [str(result.path), str(target_pf.path)],
                })
                break  # one flag per circular pair

    return flags


# ponytail: Phase 2 risk types deferred (need data parsers don't provide yet):
#   none_return_unchecked (high) — needs function body AST analysis
#   uncaught_exception (medium) — needs try/except pattern analysis
#   missing_type_annotation (low) — needs return type extraction
#   unused_parameter (low) — needs param usage analysis
#   dead_code (medium) — needs call graph (callers not populated yet)
# §9 conservative rules for Phase 2:
#   - Don't flag none_return_unchecked if caller guards: `if result:`,
#     `if result is not None:`, `assert result is not None`, `result or default`.
#   - Don't flag circular import if it's a lazy import (inside a function body).


if __name__ == "__main__":
    from pathlib import Path

    from .ast_parser import ParsedImport

    # star_import universal
    with_star = ParseResult(
        path=Path("m.py"),
        imports=[ParsedImport(target="a", lineno=2, is_star=True)],
    )
    r = analyze_risks(with_star, [with_star])
    assert len(r) == 1 and r[0]["type"] == "star_import", r

    # no star → no risk
    no_star = ParseResult(path=Path("n.py"), imports=[ParsedImport(target="os", lineno=1)])
    assert analyze_risks(no_star, [no_star]) == []

    # circular detection
    a = ParseResult(
        path=Path("circ_a.py"),
        imports=[ParsedImport(target="circ_b", lineno=1)],
    )
    b = ParseResult(
        path=Path("circ_b.py"),
        imports=[ParsedImport(target="circ_a", lineno=1)],
    )
    risks_a = analyze_risks(a, [a, b])
    assert any(r["type"] == "circular_import_toplevel" for r in risks_a), risks_a
    # single file → no circular
    assert analyze_risks(a, [a]) == []

    # conditional import → not circular
    cond = ParseResult(
        path=Path("cond_a.py"),
        imports=[ParsedImport(target="cond_b", lineno=1, is_conditional=True)],
    )
    assert _check_circular_imports(cond, [cond]) == []

    # non-Python → no circular check
    ts = ParseResult(
        path=Path("app.ts"),
        language="typescript",
        imports=[ParsedImport(target="lib", lineno=1)],
    )
    assert _check_circular_imports(ts, [ts]) == []

    print("self-check ok")
