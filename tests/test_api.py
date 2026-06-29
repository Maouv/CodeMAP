"""Integration tests for CodeMAP server API (BLUEPRINT §13.4)."""

from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient

from codemap.ai.provider import AIError
from codemap.server.app import create_app


# --- fixtures & helpers -------------------------------------------------------

PORT = 8765


@pytest.fixture()
def simple_graph():
    return {
        "meta": {"total_files": 1, "total_functions": 1, "total_edges": 0, "has_warnings": False},
        "nodes": [
            {
                "id": "a.py",
                "type": "file",
                "path": "a.py",
                "risk_level": None,
                "risk_summary": None,
                "functions": [
                    {
                        "name": "foo",
                        "type": "function",
                        "params": [],
                        "returns": None,
                        "line_start": 1,
                        "line_end": None,
                        "criticality": None,
                        "callers": [],
                        "callees": [],
                        "decorators": [],
                        "is_private": False,
                        "is_dead_code": False,
                        "risks": [],
                        "ai_summary": None,
                    }
                ],
                "classes": [],
                "imports": [],
                "constants": [],
                "has_all_definition": False,
                "exported_names": [],
                "file_modified_at": "2026-01-01T00:00:00",
                "risks": [],
            }
        ],
        "edges": [],
        "warnings": [],
    }


@pytest.fixture()
def ai_body():
    return {"file": "a.py", "function": "foo", "line": 1, "modified_at": "2026-01-01", "source": "def foo(): pass"}


def _client(graph_data, tmp_path, port=PORT):
    app = create_app(graph_data, port=port, cache_path=tmp_path / "cache.json")
    return TestClient(app, base_url=f"http://127.0.0.1:{port}")


def _hdr(host=None, origin=None):
    h = {}
    if host:
        h["host"] = host
    if origin:
        h["origin"] = origin
    return h


# --- 1-3: GET /api/graph ------------------------------------------------------


def test_get_graph__returns_200_with_schema(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).get("/api/graph", headers=_hdr(host=f"127.0.0.1:{PORT}"))
    assert r.status_code == 200
    j = r.json()
    for k in ("meta", "nodes", "edges", "warnings"):
        assert k in j
    assert j["meta"]["total_files"] > 0


def test_get_graph__nodes_match_section7_schema(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).get("/api/graph", headers=_hdr(host=f"127.0.0.1:{PORT}"))
    node = r.json()["nodes"][0]
    for k in ("id", "type", "path", "risk_level", "functions"):
        assert k in node, f"missing {k}"
    fn = node["functions"][0]
    for k in ("name", "params", "returns", "criticality"):
        assert k in fn, f"missing {k}"


def test_get_graph__sanitized_constants_phase1_default(simple_graph, tmp_path):
    node = _client(simple_graph, tmp_path).get("/api/graph", headers=_hdr(host=f"127.0.0.1:{PORT}")).json()["nodes"][0]
    assert node["constants"] == []
    # ponytail: Phase 2 akan ekstrak constants; test akan assert DB_PASSWORD -> [REDACTED] lewat full path


# --- 4-9: security middleware --------------------------------------------------


def test_security__invalid_host_header_400(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).get("/api/graph", headers=_hdr(host="evil.com"))
    assert r.status_code == 400
    assert r.json() == {"error": "Invalid Host"}


def test_security__valid_host_passes(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).get("/api/graph", headers=_hdr(host=f"localhost:{PORT}"))
    assert r.status_code == 200


def test_security__valid_127_host_passes(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).get("/api/graph", headers=_hdr(host=f"127.0.0.1:{PORT}"))
    assert r.status_code == 200


def test_security__post_invalid_origin_403(simple_graph, tmp_path, ai_body):
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin="http://evil.com")
    )
    assert r.status_code == 403
    assert r.json() == {"error": "Forbidden"}


def test_security__post_no_origin_allowed(simple_graph, tmp_path, ai_body, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = _client(simple_graph, tmp_path).post("/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}"))
    assert r.status_code != 403


def test_security__post_valid_origin_passes(simple_graph, tmp_path, ai_body, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://localhost:{PORT}")
    )
    assert r.status_code != 403


# --- 10-16: AI summary --------------------------------------------------------


def test_ai_summary__no_api_key_returns_disabled(simple_graph, tmp_path, ai_body, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "reason": "no_api_key"}


def test_ai_summary__mocked_provider_returns_summary(simple_graph, tmp_path, ai_body, monkeypatch):
    class Fake:
        name = "fake"
        def generate_summary(self, src, ctx):
            return {"role": "r", "importance": "i", "hidden_assumption": "h"}

    monkeypatch.setattr("codemap.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    assert r.status_code == 200
    j = r.json()
    assert j["enabled"] is True and j["cached"] is False
    for k in ("role", "importance", "hidden_assumption"):
        assert k in j["summary"]
    assert j["provider"] == "fake"


def test_ai_summary__auth_failed_error_type(simple_graph, tmp_path, ai_body, monkeypatch):
    class Fake:
        name = "fake"
        def generate_summary(self, src, ctx):
            raise AIError("auth_failed")

    monkeypatch.setattr("codemap.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    j = r.json()
    assert j == {"enabled": True, "error_type": "auth_failed"}
    body_text = r.text.lower()
    assert "key" not in body_text and "apikey" not in body_text


def test_ai_summary__rate_limited_with_retry_after(simple_graph, tmp_path, ai_body, monkeypatch):
    class Fake:
        name = "fake"
        def generate_summary(self, src, ctx):
            raise AIError("rate_limited", retry_after=15)

    monkeypatch.setattr("codemap.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    j = r.json()
    assert j["error_type"] == "rate_limited" and j["retry_after"] == 15


def test_ai_summary__timeout_error_type(simple_graph, tmp_path, ai_body, monkeypatch):
    class Fake:
        name = "fake"
        def generate_summary(self, src, ctx):
            raise AIError("timeout")

    monkeypatch.setattr("codemap.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    assert r.json()["error_type"] == "timeout"


def test_ai_summary__caches_result(simple_graph, tmp_path, ai_body, monkeypatch):
    calls = 0

    class Fake:
        name = "fake"
        def generate_summary(self, src, ctx):
            nonlocal calls; calls += 1
            return {"role": "r", "importance": "i", "hidden_assumption": "h"}

    monkeypatch.setattr("codemap.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    c = _client(simple_graph, tmp_path)
    hdrs = _hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    r1 = c.post("/api/ai/summary", json=ai_body, headers=hdrs)
    assert r1.json()["cached"] is False
    r2 = c.post("/api/ai/summary", json=ai_body, headers=hdrs)
    assert r2.json()["cached"] is True
    assert calls == 1
    mode = stat.S_IMODE(os.stat(tmp_path / "cache.json").st_mode)
    assert mode == 0o600


def test_ai_summary__cache_invalidation_on_modified_at_change(simple_graph, tmp_path, ai_body, monkeypatch):
    calls = 0

    class Fake:
        name = "fake"
        def generate_summary(self, src, ctx):
            nonlocal calls; calls += 1
            return {"role": "r", "importance": "i", "hidden_assumption": "h"}

    monkeypatch.setattr("codemap.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    c = _client(simple_graph, tmp_path)
    hdrs = _hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    body2 = {**ai_body, "modified_at": "2026-02-01"}
    c.post("/api/ai/summary", json=ai_body, headers=hdrs)
    r2 = c.post("/api/ai/summary", json=body2, headers=hdrs)
    assert r2.json()["cached"] is False
    assert calls == 2
