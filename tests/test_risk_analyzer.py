"""Phase 4 risk_analyzer tests: star_import (universal) + circular_import_toplevel (Python-only)."""

from pathlib import Path

from graps.scanner import ParsedFile, ParsedImport
from graps.scanner.ast_parser import safe_parse
from graps.scanner.risk_analyzer import analyze_risks

FIXTURES = Path(__file__).parent / "fixtures"


def _parse(name):
    return safe_parse(FIXTURES / name)


# ── star_import (universal) ─────────────────────────────────────────


def test_star_import__detected():
    r = _parse("star_import.py")
    risks = analyze_risks(r, [r])
    assert any(x["type"] == "star_import" for x in risks)


def test_star_import__risk_shape():
    r = _parse("star_import.py")
    risk = analyze_risks(r, [r])[0]
    assert set(risk) == {"type", "severity", "detail", "affected_files"}
    assert str(r.path) in risk["affected_files"]


def test_simple__no_risk():
    r = _parse("simple.py")
    assert analyze_risks(r, [r]) == []


def test_circular__no_star_risk():
    # circular detection is Phase 4; these files just shouldn't trip star_import.
    for name in ("circular_a.py", "circular_b.py"):
        r = _parse(name)
        assert not any(x["type"] == "star_import" for x in analyze_risks(r, [r]))


# ── circular_import_toplevel (Python-only) ──────────────────────────


def test_circular_import__detected():
    """circular_a → circular_b, circular_b → circular_a → flag both."""
    a = _parse("circular_a.py")
    b = _parse("circular_b.py")
    all_results = [a, b]

    risks_a = analyze_risks(a, all_results)
    risks_b = analyze_risks(b, all_results)
    assert any(x["type"] == "circular_import_toplevel" for x in risks_a), risks_a
    assert any(x["type"] == "circular_import_toplevel" for x in risks_b), risks_b


def test_circular_import__severity_high():
    a = _parse("circular_a.py")
    b = _parse("circular_b.py")
    risks = analyze_risks(a, [a, b])
    circ = next(x for x in risks if x["type"] == "circular_import_toplevel")
    assert circ["severity"] == "high"
    assert len(circ["affected_files"]) == 2


def test_circular_import__single_file_no_flag():
    """Self-only result → no circular flag."""
    r = _parse("simple.py")
    assert not any(x["type"] == "circular_import_toplevel" for x in analyze_risks(r, [r]))


def test_circular_import__conditional_skipped():
    """Conditional import (try/except) = lazy → not circular."""
    a = ParsedFile(
        path=Path("a.py"),
        imports=[ParsedImport(target="b", lineno=1, is_conditional=True)],
    )
    b = ParsedFile(
        path=Path("b.py"),
        imports=[ParsedImport(target="a", lineno=1)],
    )
    risks = analyze_risks(a, [a, b])
    assert not any(x["type"] == "circular_import_toplevel" for x in risks), risks


# ── language-aware ──────────────────────────────────────────────────


def test_non_python__no_circular_check():
    """Non-Python file → circular check skipped, star_import still works."""
    ts = ParsedFile(
        path=Path("app.ts"),
        language="typescript",
        imports=[
            ParsedImport(target="lib", lineno=1),
            ParsedImport(target="styles", lineno=2, is_star=True),
        ],
    )
    lib = ParsedFile(
        path=Path("lib.ts"),
        language="typescript",
        imports=[ParsedImport(target="app", lineno=1)],
    )
    risks = analyze_risks(ts, [ts, lib])
    # star_import should fire (universal)
    assert any(x["type"] == "star_import" for x in risks), risks
    # circular should NOT fire (Python-only)
    assert not any(x["type"] == "circular_import_toplevel" for x in risks), risks


def test_external_import__no_circular():
    """Import to module not in all_results → not circular."""
    r = _parse("simple.py")  # imports os, which is not in all_results
    assert analyze_risks(r, [r]) == []
