"""Unit tests for graph_builder.build_graph (BLUEPRINT §7, §13).

Phase 1 limitation: parser does not extract constants/params/returns/classes/etc.
Schema fields with no upstream data get defaults — tests assert those defaults.
Sanitize wiring (C-01) is tested via _sanitized_constants helper directly.
"""

from datetime import datetime
from pathlib import Path

from graps.scanner.ast_parser import safe_parse
from graps.scanner.graph_builder import build_graph, _sanitized_constants


def _make_project(tmp_path):
    """Create minimal project tree, return (root, results)."""
    (tmp_path / "main.py").write_text("from services import helper\n")
    svc = tmp_path / "services"
    svc.mkdir()
    (svc / "__init__.py").write_text("")
    (svc / "helper.py").write_text("def hello(name: str) -> str:\n    return f'hi {name}'\n")
    (tmp_path / "star.py").write_text("from os import *\n")
    results = [safe_parse(p) for p in sorted(tmp_path.rglob("*.py"))]
    return tmp_path, results


def test_build_graph__returns_schema_keys(tmp_path):
    root, results = _make_project(tmp_path)
    g = build_graph(results, root)
    assert set(g.keys()) == {"meta", "nodes", "edges", "warnings"}


def test_build_graph__meta_counts_correct(tmp_path):
    root, results = _make_project(tmp_path)
    m = build_graph(results, root)["meta"]
    assert m["total_files"] == 4
    assert m["total_functions"] == 1
    assert m["total_edges"] >= 1


def test_build_graph__meta_has_scanned_at(tmp_path):
    root, results = _make_project(tmp_path)
    m = build_graph(results, root)["meta"]
    datetime.fromisoformat(m["scanned_at"])  # raises if not ISO-8601


def test_build_graph__node_has_id_relative_to_root(tmp_path):
    root, results = _make_project(tmp_path)
    nodes = {n["id"]: n for n in build_graph(results, root)["nodes"]}
    assert "services/helper.py" in nodes
    assert not any(n["id"].startswith("/") for n in nodes.values()), "M-03: absolute path leak"


def test_build_graph__node_function_shape(tmp_path):
    root, results = _make_project(tmp_path)
    nodes = {n["id"]: n for n in build_graph(results, root)["nodes"]}
    fns = nodes["services/helper.py"]["functions"]
    hello = fns[0]
    assert hello["name"] == "hello"
    assert hello["type"] == "function"
    assert hello["decorators"] == []
    assert hello["is_private"] is False
    assert isinstance(hello["line_start"], int)
    assert hello["params"] == []
    assert hello["returns"] is None
    assert hello["line_end"] is None
    assert hello["callers"] == []
    assert hello["callees"] == []
    assert hello["is_dead_code"] is False
    assert hello["risks"] == []
    assert hello["ai_summary"] is None


def test_build_graph__private_function_detected(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "priv.py").write_text("def _hidden(): pass\n")
    results = [safe_parse(p) for p in root.rglob("*.py")]
    fns = build_graph(results, root)["nodes"][0]["functions"]
    assert fns[0]["is_private"] is True


def test_build_graph__edge_shape(tmp_path):
    root, results = _make_project(tmp_path)
    edges = build_graph(results, root)["edges"]
    assert len(edges) >= 1
    e = edges[0]
    assert "source" in e and "target" in e
    assert e["type"] == "imports"
    assert e["weight"] >= 1
    assert isinstance(e["imported_names"], list)
    assert not e["source"].startswith("/") and not e["target"].startswith("/")


def test_build_graph__star_import_emits_warning_no_edge(tmp_path):
    root, results = _make_project(tmp_path)
    g = build_graph(results, root)
    star_srcs = {e["source"] for e in g["edges"]}
    assert "star.py" not in star_srcs
    star_warns = [w for w in g["warnings"] if w["type"] == "star_import"]
    assert any(w["file"] == "star.py" for w in star_warns)


def test_build_graph__constants_default_empty(tmp_path):
    root, results = _make_project(tmp_path)
    nodes = build_graph(results, root)["nodes"]
    assert all(n["constants"] == [] for n in nodes)
    # ponytail: Phase 2 — saat parser ekstrak constants, ganti test ini ke assert constants ter-extract


def test_sanitized_constants__redacts_db_password():
    out = _sanitized_constants([{"name": "DB_PASSWORD", "value": "hunter2", "line": 1}])
    assert out[0]["value"] == "[REDACTED]"


def test_sanitized_constants__preserves_safe_constant():
    out = _sanitized_constants([{"name": "MAX_RETRY", "value": "3", "line": 1}])
    assert out[0]["value"] == "3"


def test_sanitized_constants__redacts_api_key_pattern():
    out = _sanitized_constants([{"name": "FOO", "value": "sk-ant-abc123def456ghi789jkl012mno345", "line": 1}])
    assert out[0]["value"] == "[REDACTED]"


def test_build_graph__risk_level_default_none(tmp_path):
    root, results = _make_project(tmp_path)
    nodes = build_graph(results, root)["nodes"]
    assert all(n["risk_level"] is None for n in nodes)


def test_build_graph__risks_list_contains_star_import(tmp_path):
    root, results = _make_project(tmp_path)
    nodes = {n["id"]: n for n in build_graph(results, root)["nodes"]}
    star_risks = nodes["star.py"]["risks"]
    assert any(r["type"] == "star_import" and r["severity"] == "medium" for r in star_risks)
