"""Tests untuk ``AIProvider.chat`` — Phase 5 refactor (generate_summary → chat).

scrub_secrets + _build_prompt + _parse_summary dihapus (Option C — context
dikirim raw; build_ai_context di server yang assemble context). Tests scrub
dihapus, ganti dengan test ``chat()``: raw text return, error mapping, dispatch.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from graps.ai.provider import (
    AIError,
    AIProvider,
    AnthropicProvider,
    OpenAIProvider,
    get_provider,
)


# --- helpers: fake SDK module -----------------------------------------------


def _install_fake_anthropic(monkeypatch, *, raise_on_import=False):
    """Inject fake ``anthropic`` module into sys.modules + return exception classes."""
    if raise_on_import:
        monkeypatch.setitem(sys.modules, "anthropic", None)  # ImportError on import
        return None

    class AuthenticationError(Exception):
        pass

    class RateLimitError(Exception):
        def __init__(self, response=None):
            self.response = response

    class APITimeoutError(Exception):
        pass

    mod = types.ModuleType("anthropic")
    mod.AuthenticationError = AuthenticationError
    mod.RateLimitError = RateLimitError
    mod.APITimeoutError = APITimeoutError

    class _Messages:
        def __init__(self, create):
            self.create = create

    class _Content:
        def __init__(self, text):
            self.text = text

    class _Resp:
        def __init__(self, text):
            self.content = [_Content(text)]

    class _Client:
        def __init__(self, create):
            self.messages = _Messages(create)

    mod.Anthropic = lambda **kw: _Client(mod._create)  # type: ignore[attr-defined]
    mod._create = None  # patched per-test
    mod._Resp = _Resp
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return mod


def _install_fake_openai(monkeypatch, *, raise_on_import=False):
    if raise_on_import:
        monkeypatch.setitem(sys.modules, "openai", None)
        return None

    class AuthenticationError(Exception):
        pass

    class RateLimitError(Exception):
        def __init__(self, response=None):
            self.response = response

    class APITimeoutError(Exception):
        pass

    mod = types.ModuleType("openai")
    mod.AuthenticationError = AuthenticationError
    mod.RateLimitError = RateLimitError
    mod.APITimeoutError = APITimeoutError

    class _Msg:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content):
            self.message = _Msg(content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    class _Completions:
        def __init__(self, create):
            self.create = create

    class _Chat:
        def __init__(self, create):
            self.completions = _Completions(create)

    class _Client:
        def __init__(self, create):
            self.chat = _Chat(create)

    mod.OpenAI = lambda **kw: _Client(mod._create)  # type: ignore[attr-defined]
    mod._create = None
    mod._Resp = _Resp
    monkeypatch.setitem(sys.modules, "openai", mod)
    return mod


# --- chat() return raw text -------------------------------------------------


def test_chat__anthropic_returns_raw_text(monkeypatch):
    mod = _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return mod._Resp("debug answer text")

    mod._create = _create
    out = AnthropicProvider().chat([{"role": "user", "content": "hi"}], "ctx here")
    assert out == "debug answer text"  # raw string, NOT dict
    assert captured["system"] == "ctx here"  # context as system message
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["max_tokens"] == 1024


def test_chat__openai_returns_raw_text(monkeypatch):
    mod = _install_fake_openai(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return mod._Resp("openai raw reply")

    mod._create = _create
    out = OpenAIProvider().chat([{"role": "user", "content": "hi"}], "ctx")
    assert out == "openai raw reply"
    # OpenAI: context as first system message, then user messages.
    assert captured["messages"][0] == {"role": "system", "content": "ctx"}
    assert captured["messages"][1] == {"role": "user", "content": "hi"}


# --- error mapping ----------------------------------------------------------


def test_chat__anthropic_auth_failed(monkeypatch):
    mod = _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    mod._create = MagicMock(side_effect=mod.AuthenticationError())
    with pytest.raises(AIError) as ei:
        AnthropicProvider().chat([{"role": "user", "content": "x"}], "")
    assert ei.value.error_type == "auth_failed"


def test_chat__anthropic_rate_limited_with_retry_after(monkeypatch):
    mod = _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    class _RespHeaders:
        headers = {"retry-after": "15"}

    mod._create = MagicMock(side_effect=mod.RateLimitError(response=_RespHeaders()))
    with pytest.raises(AIError) as ei:
        AnthropicProvider().chat([{"role": "user", "content": "x"}], "")
    assert ei.value.error_type == "rate_limited"
    assert ei.value.retry_after == 15


def test_chat__anthropic_timeout(monkeypatch):
    mod = _install_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    mod._create = MagicMock(side_effect=mod.APITimeoutError())
    with pytest.raises(AIError) as ei:
        AnthropicProvider().chat([{"role": "user", "content": "x"}], "")
    assert ei.value.error_type == "timeout"


def test_chat__sdk_not_installed(monkeypatch):
    _install_fake_anthropic(monkeypatch, raise_on_import=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    with pytest.raises(AIError) as ei:
        AnthropicProvider().chat([{"role": "user", "content": "x"}], "")
    assert ei.value.error_type == "sdk_not_installed"


def test_chat__auth_failed_when_no_api_key(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AIError) as ei:
        AnthropicProvider().chat([{"role": "user", "content": "x"}], "")
    assert ei.value.error_type == "auth_failed"


# --- get_provider dispatch (unchanged) --------------------------------------


def test_get_provider__dispatch(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_provider() is None

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    assert isinstance(get_provider(), AnthropicProvider)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert isinstance(get_provider(), OpenAIProvider)


def test_aiprovider_chat_not_implemented():
    with pytest.raises(NotImplementedError):
        AIProvider().chat([], "")
