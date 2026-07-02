"""Integration tests for graps server API (BLUEPRINT §13.4).

Phase 5: ``/api/ai/summary`` deprecated (keep route, return deprecation).
``/api/ai/chat`` endpoint baru (stateless, build_ai_context + provider.chat).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from graps.ai.provider import AIError
from graps.server.app import build_ai_context, create_app


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


def _client(graph_data, tmp_path, port=PORT, scan_root=None):
    app = create_app(graph_data, port=port, cache_path=tmp_path / "cache.json", scan_root=scan_root)
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


def test_security__post_origin_prefix_bypass_rejected_403(simple_graph, tmp_path, ai_body):
    # CSRF guard must exact-match Origin, not startswith() (report-bug-server Finding 1).
    attack_origins = [
        f"http://localhost:{PORT}.evil.com",
        f"http://localhost:{PORT}@evil.com",
        f"http://localhost:{PORT}x",
        f"http://127.0.0.1:{PORT}.attacker.com",
        f"http://127.0.0.1:{PORT}@attacker.com",
    ]
    for origin in attack_origins:
        r = _client(simple_graph, tmp_path).post(
            "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=origin)
        )
        assert r.status_code == 403, f"bypass leaked for origin={origin!r}: {r.status_code}"
        assert r.json() == {"error": "Forbidden"}


def test_security__post_no_origin_rejected_403(simple_graph, tmp_path, ai_body):
    # Fail-closed CSRF guard: no Origin header → 403 (report-bug-finder Finding 2).
    r = _client(simple_graph, tmp_path).post("/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}"))
    assert r.status_code == 403
    assert r.json() == {"error": "Forbidden"}


def test_security__chat_post_invalid_origin_403(simple_graph, tmp_path):
    # Chat juga POST → CSRF guard tetap jalan.
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat", json={"message": "hi"}, headers=_hdr(host=f"127.0.0.1:{PORT}", origin="http://evil.com")
    )
    assert r.status_code == 403
    assert r.json() == {"error": "Forbidden"}


def test_security__chat_post_no_origin_rejected_403(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).post("/api/ai/chat", json={"message": "hi"}, headers=_hdr(host=f"127.0.0.1:{PORT}"))
    assert r.status_code == 403


def test_security__post_valid_origin_passes(simple_graph, tmp_path, ai_body, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://localhost:{PORT}")
    )
    assert r.status_code != 403


# --- /api/ai/summary DEPRECATED (Phase 5) ------------------------------------


def test_ai_summary__deprecated_response(simple_graph, tmp_path, ai_body):
    # Route tetap, return deprecation response (logic provider/cache tidak jalan).
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/summary", json=ai_body, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    assert r.status_code == 200
    assert r.json() == {"deprecated": True, "reason": "use /api/ai/chat"}


# --- /api/ai/chat (Phase 5) --------------------------------------------------


def test_chat__empty_message_rejected(simple_graph, tmp_path):
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat", json={"message": "   "}, headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}")
    )
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "reason": "empty_message", "warnings": []}


def test_chat__no_api_key_returns_disabled(simple_graph, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat", json={"message": "why?", "tagged": ["a.py"]},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    assert r.status_code == 200
    j = r.json()
    assert j["enabled"] is False and j["reason"] == "no_api_key", j
    # no scan_root → build_ai_context returns ("", []).
    assert j["warnings"] == [], j


def test_chat__mocked_provider_returns_reply(simple_graph, tmp_path, monkeypatch):
    captured = {}

    class Fake:
        name = "fake"
        def chat(self, messages, context):
            captured["messages"] = messages
            captured["context"] = context
            return "debug answer"

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat",
        json={"message": "why foo?", "tagged": [], "history": [{"role": "assistant", "content": "hi"}]},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert j["enabled"] is True and j["reply"] == "debug answer", j
    # history + message appended.
    assert captured["messages"] == [
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "why foo?"},
    ], captured["messages"]


def test_chat__mocked_auth_failed(simple_graph, tmp_path, monkeypatch):
    class Fake:
        name = "fake"
        def chat(self, messages, context):
            raise AIError("auth_failed")

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat", json={"message": "hi"},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert j["enabled"] is True and j["error_type"] == "auth_failed", j
    body_text = r.text.lower()
    assert "key" not in body_text and "apikey" not in body_text


def test_chat__rate_limited_with_retry_after(simple_graph, tmp_path, monkeypatch):
    class Fake:
        name = "fake"
        def chat(self, messages, context):
            raise AIError("rate_limited", retry_after=15)

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat", json={"message": "hi"},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert j["error_type"] == "rate_limited" and j["retry_after"] == 15, j


def test_chat__sdk_not_installed_returns_disabled(simple_graph, tmp_path, monkeypatch):
    class Fake:
        name = "fake"
        def chat(self, messages, context):
            raise AIError("sdk_not_installed")

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path).post(
        "/api/ai/chat", json={"message": "hi"},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert j["enabled"] is False and j["reason"] == "sdk_not_installed", j


# --- build_ai_context + scan_root --------------------------------------------


def test_chat__build_context_with_scan_root(simple_graph, tmp_path, monkeypatch):
    # Tulis source asli ke scan_root (tmp_path) supaya build_ai_context baca disk.
    (tmp_path / "a.py").write_text("def foo():\n    return 42\n\ndef bar(): pass\n")
    # Update graph dengan line_end supaya function body di-extract presisi.
    graph = {
        **simple_graph,
        "nodes": [{
            **simple_graph["nodes"][0],
            "functions": [{
                **simple_graph["nodes"][0]["functions"][0],
                "line_start": 1, "line_end": 2,
            }],
        }],
    }
    captured = {}

    class Fake:
        name = "fake"
        def chat(self, messages, context):
            captured["context"] = context
            return "ok"

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(graph, tmp_path, scan_root=tmp_path).post(
        "/api/ai/chat", json={"message": "why 42?", "tagged": ["a.py::foo"]},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert j["enabled"] is True and j["reply"] == "ok", j
    # context mengandung function body dari disk (hanya foo, bukan bar).
    assert "def foo" in captured["context"], captured["context"]
    assert "return 42" in captured["context"], captured["context"]
    assert "def bar" not in captured["context"], captured["context"]


def test_chat__credential_file_excluded(simple_graph, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SECRET=hunter2\nDB_PASSWORD=hunter3")
    captured = {}

    class Fake:
        name = "fake"
        def chat(self, messages, context):
            captured["context"] = context
            return "ok"

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path, scan_root=tmp_path).post(
        "/api/ai/chat", json={"message": "x", "tagged": [".env"]},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert any(w["reason"] == "credential_file_excluded" for w in j["warnings"]), j
    assert "hunter2" not in captured["context"], captured["context"]
    assert "hunter3" not in captured["context"], captured["context"]


def test_chat__no_scan_root_empty_context(simple_graph, tmp_path, monkeypatch):
    # scan_root=None → build_ai_context return ("", []) — backward-compat test.
    captured = {}

    class Fake:
        name = "fake"
        def chat(self, messages, context):
            captured["context"] = context
            return "ok"

    monkeypatch.setattr("graps.ai.provider.get_provider", lambda: Fake())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = _client(simple_graph, tmp_path, scan_root=None).post(
        "/api/ai/chat", json={"message": "hi", "tagged": ["a.py"]},
        headers=_hdr(host=f"127.0.0.1:{PORT}", origin=f"http://127.0.0.1:{PORT}"),
    )
    j = r.json()
    assert j["enabled"] is True and j["reply"] == "ok", j
    assert captured["context"] == "", captured["context"]
    assert j["warnings"] == [], j


# --- build_ai_context unit (isolated) ----------------------------------------


def test_build_ai_context__empty_when_no_tagged(simple_graph, tmp_path):
    ctx, warns = build_ai_context([], simple_graph, tmp_path)
    assert ctx == "" and warns == []


def test_build_ai_context__empty_when_no_scan_root(simple_graph, tmp_path):
    ctx, warns = build_ai_context(["a.py"], simple_graph, None)
    assert ctx == "" and warns == []


def test_build_ai_context__credential_file_warning(simple_graph, tmp_path):
    (tmp_path / ".env").write_text("SECRET=x")
    ctx, warns = build_ai_context([".env"], simple_graph, tmp_path)
    assert any(w["reason"] == "credential_file_excluded" for w in warns), warns
    assert "SECRET=x" not in ctx, ctx


def test_build_ai_context__file_not_in_graph_warning(simple_graph, tmp_path):
    (tmp_path / "unknown.py").write_text("x = 1")
    ctx, warns = build_ai_context(["unknown.py"], simple_graph, tmp_path)
    assert any(w["reason"] == "file_not_in_graph" for w in warns), warns
