"""Phase 1 risk_analyzer tests: star_import detection only."""

from pathlib import Path

from codemap.scanner.ast_parser import safe_parse
from codemap.scanner.risk_analyzer import analyze_risks

FIXTURES = Path(__file__).parent / "fixtures"


def _parse(name):
    return safe_parse(FIXTURES / name)


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
    # circular detection is Phase 2; these files just shouldn't trip star_import.
    for name in ("circular_a.py", "circular_b.py"):
        r = _parse(name)
        assert analyze_risks(r, [r]) == []
