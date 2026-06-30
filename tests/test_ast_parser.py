"""Unit tests for ast_parser.safe_parse (BLUEPRINT §13.3).

Aligned to actual module behavior: safe_parse always returns ParseResult
(never None), warnings are plain strings. TYPE_CHECKING imports are NOT
flagged conditional (module only tracks try-body depth).
"""

import ast
from pathlib import Path

from graps.scanner import ast_parser
from graps.scanner.ast_parser import safe_parse

FIX = Path(__file__).parent / "fixtures"


def test_parse_simple__extracts_function():
    fns = safe_parse(FIX / "simple.py").functions
    assert [f.name for f in fns] == ["hello"]
    assert fns[0].is_nested is False


def test_parse_simple__extracts_import():
    imps = safe_parse(FIX / "simple.py").imports
    assert [i.target for i in imps] == ["os"]
    assert imps[0].is_star is False


def test_parse_star_import__flags_is_star():
    r = safe_parse(FIX / "star_import.py")
    assert r.imports[0].is_star is True
    assert any("star import" in w for w in r.warnings)


def test_parse_dynamic_import__emits_warning():
    r = safe_parse(FIX / "dynamic_import.py")
    assert any("importlib" in w for w in r.warnings)
    assert any(i.is_dynamic for i in r.imports)


def test_parse_conditional_import__both_branches():
    imps = safe_parse(FIX / "conditional_import.py").imports
    assert {i.target for i in imps} == {"ujson", "json"}
    assert all(i.is_conditional for i in imps)


def test_parse_nested_functions__inner_not_toplevel():
    fns = {f.name: f for f in safe_parse(FIX / "nested_functions.py").functions}
    assert fns["outer"].is_nested is False
    assert fns["inner"].is_nested is True


def test_parse_decorators__detects_property():
    fns = {f.name: f for f in safe_parse(FIX / "decorators.py").functions}
    assert fns["p"].is_property is True
    assert "property" in fns["p"].decorators


def test_parse_type_checking__import_extracted():
    # Module has no visit_If, so TYPE_CHECKING import is plain, not conditional.
    imps = {i.target: i for i in safe_parse(FIX / "type_checking.py").imports}
    assert "models.User" in imps
    assert imps["models.User"].is_conditional is False


def test_parse_all_definition__overrides_exports():
    assert safe_parse(FIX / "all_definition.py").exported_names == ["public"]


def test_parse_syntax_error__warns_no_raise():
    r = safe_parse(FIX / "syntax_error.py")  # must not raise
    assert any("parse failed" in w for w in r.warnings)


def test_safe_parse__large_file_skipped(tmp_path):
    f = tmp_path / "big.py"
    f.write_text("x = 1\n" * 200_000)
    assert any("too large" in w for w in safe_parse(f).warnings)


def test_safe_parse__size_guard_at_boundary(tmp_path):
    ok = tmp_path / "ok.py"
    ok.write_text("#" * 999_999 + "\n")  # exactly 1_000_000 bytes, valid python
    assert not any("too large" in w for w in safe_parse(ok).warnings)
    big = tmp_path / "over.py"
    big.write_text("#" * 1_000_000 + "\n")  # 1_000_001 bytes
    assert any("too large" in w for w in safe_parse(big).warnings)


def test_safe_parse__syntax_error_returns_warning(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("def broken(:\n")
    assert any("parse failed" in w for w in safe_parse(f).warnings)


def test_safe_parse__timeout_returns_warning(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise TimeoutError
    monkeypatch.setattr(ast_parser.ast, "parse", boom)
    f = tmp_path / "t.py"
    f.write_text("x = 1\n")
    assert any("TimeoutError" in w for w in safe_parse(f).warnings)


def test_safe_parse__memory_error_no_crash(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise MemoryError
    monkeypatch.setattr(ast_parser.ast, "parse", boom)
    f = tmp_path / "m.py"
    f.write_text("x = 1\n")
    assert any("MemoryError" in w for w in safe_parse(f).warnings)


def test_parse_latin1_encoded__detects_encoding():
    # Bytes are latin-1 with a coding cookie; must not crash on decode.
    assert safe_parse(FIX / "latin1_encoded.py").warnings == []


def test_parse_exec_eval__emits_warning():
    warns = safe_parse(FIX / "exec_eval.py").warnings
    assert any("exec" in w for w in warns)
    assert any("eval" in w for w in warns)
