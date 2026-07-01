"""Static risk flags — Layer 1 (BLUEPRINT Section 9). Phase 1: star_import only."""

from __future__ import annotations

from .ast_parser import ParseResult


def analyze_risks(result: ParseResult, all_results: list[ParseResult]) -> list[dict[str, object]]:
    """Return risk dicts for `result`. Phase 1 implements only star_import (§9)."""
    risks: list[dict[str, object]] = []
    for imp in result.imports:
        if imp.is_star:
            risks.append({
                "type": "star_import",
                "severity": "medium",  # §9 table
                "detail": f"star import from {imp.target!r} (line {imp.lineno})",
                "affected_files": [str(result.path)],
            })
    return risks


# ponytail: Phase 2 risk types deferred (not implemented here). Implementor adds:
#   none_return_unchecked (high), uncaught_exception (medium), dead_code (medium),
#   circular_import_toplevel (high), missing_type_annotation (low),
#   unused_parameter (low). dead_code/circular need `all_results` (cross-file).
# §9 conservative rules for Phase 2:
#   - Don't flag none_return_unchecked if caller guards: `if result:`,
#     `if result is not None:`, `assert result is not None`, `result or default`.
#   - Don't flag circular import if it's a lazy import (inside a function body).


if __name__ == "__main__":
    from pathlib import Path

    from .ast_parser import ParsedImport

    with_star = ParseResult(
        path=Path("m.py"),
        imports=[ParsedImport(target="a", lineno=2, is_star=True)],
    )
    r = analyze_risks(with_star, [with_star])
    assert len(r) == 1 and r[0]["type"] == "star_import", r

    no_star = ParseResult(path=Path("n.py"), imports=[ParsedImport(target="os", lineno=1)])
    assert analyze_risks(no_star, [no_star]) == []

    print("self-check ok")
