"""Abstraksi AI provider untuk graps (lihat BLUEPRINT.md §10).

Modul ini hanya bertugas: terima conversation + context string, panggil SDK
provider yang sesuai, kembalikan raw text reply. Cache, retry, dan endpoint
adalah urusan caller.

Phase 5: scrub_secrets + _build_prompt + _parse_summary dihapus (Option C —
context dikirim raw; server-side build_ai_context yang assemble context).

Aturan keamanan:
- API key TIDAK pernah disimpan sebagai instance attribute. Dibaca dari env
  setiap kali ``chat`` dipanggil.
- Exception dari SDK di-map ke :class:`AIError` dengan ``error_type`` enum
  pendek — pesan asli tidak pernah di-log atau di-propagate karena bisa
  membawa fragment API key.
- ``context`` dikirim raw apa adanya; secret handling adalah tanggung jawab
  caller (build_ai_context di server/app.py — credential file hard-excluded).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class AIError(Exception):
    """Exception sanitized untuk caller.

    ``error_type`` adalah salah satu:
    ``"auth_failed" | "rate_limited" | "timeout" | "sdk_not_installed"
    | "unknown"``. (``parse_failed`` dihapus Phase 5 — chat return raw text.)
    Pesan asli dari SDK sengaja tidak diteruskan.
    """

    def __init__(self, error_type: str, retry_after: int | None = None):
        super().__init__(error_type)
        self.error_type = error_type
        self.retry_after = retry_after


def _retry_after_from_headers(e: BaseException) -> int | None:
    """Ambil ``retry-after`` header dari exception response, kalau ada.

    ponytail: helper shared Anthropic + OpenAI — keduanya punya
    ``e.response.headers`` shape sama. ``None`` kalau tidak ada/bukan int.
    """
    resp_obj = getattr(e, "response", None)
    if resp_obj is None:
        return None
    headers = getattr(resp_obj, "headers", {}) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


class AIProvider:
    """Base class. ``NotImplementedError`` di ``chat`` sudah cukup sebagai
    kontrak — tidak perlu :mod:`abc`.
    """

    model: str = ""
    name: str = ""

    def chat(self, messages: list[dict[str, str]], context: str) -> str:
        """Kirim conversation ke provider. Return raw text reply.

        messages: ``[{"role": "user"|"assistant", "content": "..."}]``
        context:  string context system (graph metadata + source) — dikirim
                  sebagai system message, BUKAN scrub (Option C).
        """
        raise NotImplementedError


class AnthropicProvider(AIProvider):
    model = "claude-haiku-4-5-20251001"
    name = "anthropic"

    def chat(self, messages: list[dict[str, str]], context: str) -> str:
        # ponytail: lazy import — SDK adalah optional extra (BLUEPRINT Phase 1).
        try:
            import anthropic
        except ImportError:
            raise AIError("sdk_not_installed")

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise AIError("auth_failed")

        try:
            client = anthropic.Anthropic(api_key=key, timeout=30.0)
            resp = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=context,
                messages=messages,
            )
            text = resp.content[0].text
        except anthropic.AuthenticationError as e:
            logger.warning(type(e).__name__)
            raise AIError("auth_failed")
        except anthropic.RateLimitError as e:
            logger.warning(type(e).__name__)
            raise AIError("rate_limited", retry_after=_retry_after_from_headers(e))
        except anthropic.APITimeoutError as e:
            logger.warning(type(e).__name__)
            raise AIError("timeout")
        except Exception as e:
            logger.warning(type(e).__name__)
            raise AIError("unknown")

        return text  # raw string, BUKAN dict 3-field


class OpenAIProvider(AIProvider):
    model = "gpt-4o-mini"
    name = "openai"

    def chat(self, messages: list[dict[str, str]], context: str) -> str:
        # ponytail: lazy import — SDK adalah optional extra.
        try:
            import openai
            from openai import OpenAI
        except ImportError:
            raise AIError("sdk_not_installed")

        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise AIError("auth_failed")

        try:
            client = OpenAI(api_key=key, timeout=30.0)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": context}, *messages],
            )
            text = resp.choices[0].message.content
        except openai.AuthenticationError as e:
            logger.warning(type(e).__name__)
            raise AIError("auth_failed")
        except openai.RateLimitError as e:
            logger.warning(type(e).__name__)
            raise AIError("rate_limited", retry_after=_retry_after_from_headers(e))
        except openai.APITimeoutError as e:
            logger.warning(type(e).__name__)
            raise AIError("timeout")
        except Exception as e:
            logger.warning(type(e).__name__)
            raise AIError("unknown")

        return text  # raw string, BUKAN dict 3-field


def get_provider() -> AIProvider | None:
    """Pilih provider berdasarkan env var. Anthropic dulu, OpenAI fallback."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return None


if __name__ == "__main__":
    # Self-check: dispatch + error contract. Tidak panggil SDK beneran.
    saved = {
        "ANTHROPIC_API_KEY": os.environ.pop("ANTHROPIC_API_KEY", None),
        "OPENAI_API_KEY": os.environ.pop("OPENAI_API_KEY", None),
    }
    try:
        # 1. Env kosong -> None.
        assert get_provider() is None

        # 2. Hanya ANTHROPIC_API_KEY -> AnthropicProvider, no api_key attr.
        os.environ["ANTHROPIC_API_KEY"] = "dummy"
        p = get_provider()
        assert isinstance(p, AnthropicProvider)
        assert not hasattr(p, "api_key")
        del os.environ["ANTHROPIC_API_KEY"]

        # 3. Hanya OPENAI_API_KEY -> OpenAIProvider.
        os.environ["OPENAI_API_KEY"] = "dummy"
        p = get_provider()
        assert isinstance(p, OpenAIProvider)
        del os.environ["OPENAI_API_KEY"]

        # 4. AIError membawa error_type + retry_after.
        assert AIError("auth_failed").error_type == "auth_failed"
        assert AIError("rate_limited", retry_after=5).retry_after == 5

        # 5. Base AIProvider.chat raises NotImplementedError.
        try:
            AIProvider().chat([], "")
        except NotImplementedError:
            pass
        else:
            raise AssertionError("AIProvider.chat should raise NotImplementedError")

        # 6. AnthropicProvider.chat tanpa key -> auth_failed (hanya kalau SDK terpasang;
        #    ponytail: optional extra — self-check tidak boleh gagal kalau SDK absen).
        try:
            import anthropic  # noqa: F401
            _has_anthropic = True
        except ImportError:
            _has_anthropic = False
        if _has_anthropic:
            os.environ["ANTHROPIC_API_KEY"] = ""
            try:
                AnthropicProvider().chat([{"role": "user", "content": "hi"}], "ctx")
            except AIError as e:
                assert e.error_type == "auth_failed", e.error_type
            else:
                raise AssertionError("expected auth_failed on missing key")
            del os.environ["ANTHROPIC_API_KEY"]

        # 7. _retry_after_from_headers parses int / None.
        class _Resp:
            headers = {"retry-after": "30"}

        class _Err(Exception):
            response = _Resp()

        assert _retry_after_from_headers(_Err()) == 30

        class _Err2(Exception):
            response = None

        assert _retry_after_from_headers(_Err2()) is None

        print("provider.py self-check OK")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
