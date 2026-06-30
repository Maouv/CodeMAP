"""Abstraksi AI provider untuk graps (lihat BLUEPRINT.md §10).

Modul ini hanya bertugas: terima source code + konteks function, scrub secret,
panggil SDK provider yang sesuai, kembalikan dict ringkas
``{"role", "importance", "hidden_assumption"}``. Cache, retry, dan endpoint
adalah urusan caller.

Aturan keamanan:
- API key TIDAK pernah disimpan sebagai instance attribute. Dibaca dari env
  setiap kali ``generate_summary`` dipanggil.
- Exception dari SDK di-map ke :class:`AIError` dengan ``error_type`` enum
  pendek — pesan asli tidak pernah di-log atau di-propagate karena bisa
  membawa fragment API key.
- ``scrub_secrets`` selalu dijalankan terhadap source sebelum dimasukkan ke
  prompt.
"""

from __future__ import annotations

import json
import logging
import os
import re

try:
    from detect_secrets.plugins.aws import AWSKeyDetector
    from detect_secrets.plugins.github_token import GitHubTokenDetector
    from detect_secrets.plugins.high_entropy_strings import (
        Base64HighEntropyString,
        HexHighEntropyString,
    )
    from detect_secrets.plugins.jwt import JwtTokenDetector
    from detect_secrets.plugins.keyword import KeywordDetector
    from detect_secrets.plugins.stripe import StripeDetector

    # Layer-1 detector (PHASE3 Task 1). Module-level: instantiate sekali.
    _DETECTORS = [
        AWSKeyDetector(),
        GitHubTokenDetector(),
        StripeDetector(),
        JwtTokenDetector(),
        KeywordDetector(),
        Base64HighEntropyString(limit=4.5),
        HexHighEntropyString(limit=3.0),
    ]
except ImportError:
    # ponytail: detect-secrets adalah optional [ai] extra, bukan core dep.
    # Ceiling: tanpa-nya hanya layer-2 regex jalan (coverage 3 keyword, false
    # negative tinggi). Upgrade path: ``pip install graps[ai]``. Guard ini
    # wajib karena server/app.py import modul ini di top-level — tanpa guard,
    # ``pip install graps`` (core) crash saat import.
    _DETECTORS = []

logger = logging.getLogger(__name__)

# Pola dari BLUEPRINT §10. Compile sekali di module level.
_SENSITIVE_PATTERNS = [
    re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\']?.+'),
    re.compile(r'(?i)(api_key|apikey|secret|token)\s*=\s*["\']?.+'),
    re.compile(r'(?i)(auth|credential)\s*=\s*["\']?.+'),
]


def scrub_secrets(source: str) -> str:
    """Redact credential sebelum dikirim ke AI. Dua layer defense-in-depth.

    Layer 1: detect-secrets plugins (AWS key, GitHub/Stripe/JWT token, keyword,
    high-entropy string) — redact setiap ``secret.secret_value`` per line.
    Layer 2: regex manual ``_SENSITIVE_PATTERNS`` — fallback untuk pattern yang
    plugin lewatkan (mis. ``token = "..."`` yang ``secret_value``-nya hanya
    prefix ``ghp``); juga satu-satunya layer kalau detect-secrets tidak terpasang.
    """
    redacted_lines = []
    for line in source.split("\n"):
        redacted = line
        for detector in _DETECTORS:
            try:
                secrets = detector.analyze_line(
                    filename="<ai_summary_input>",
                    line=line,
                    line_number=0,
                )
            except Exception:
                # ponytail: ceiling = satu detector/line di-skip; never crash redaction.
                continue
            for secret in secrets or []:
                if secret.secret_value:
                    redacted = redacted.replace(secret.secret_value, "[REDACTED]")
        redacted_lines.append(redacted)

    scrubbed = "\n".join(redacted_lines)

    # Layer 2 — regex manual lama, tetap jalan sebagai fallback (defense in depth).
    for pattern in _SENSITIVE_PATTERNS:
        scrubbed = pattern.sub(
            lambda m: m.group().split("=")[0] + '= "[REDACTED]"', scrubbed
        )
    return scrubbed


class AIError(Exception):
    """Exception sanitized untuk caller.

    ``error_type`` adalah salah satu:
    ``"auth_failed" | "rate_limited" | "timeout" | "sdk_not_installed"
    | "parse_failed" | "unknown"``.
    Pesan asli dari SDK sengaja tidak diteruskan.
    """

    def __init__(self, error_type: str, retry_after: int | None = None):
        super().__init__(error_type)
        self.error_type = error_type
        self.retry_after = retry_after


def _build_prompt(file_content: str, function_context: dict) -> str:
    """Susun prompt single-shot yang minta JSON tiga-field.

    ``function_context`` minimal punya ``name``, ``file``, ``line``.
    """
    name = function_context.get("name", "?")
    file_ = function_context.get("file", "?")
    line = function_context.get("line", "?")
    return (
        f"Analyze function `{name}` defined in `{file_}` (line {line}). "
        "Reply with a single JSON object containing exactly these string "
        "fields: `role` (one sentence describing what this function does in "
        "the system), `importance` (why other code depends on it / what "
        "breaks if it changes), `hidden_assumption` (an implicit precondition "
        "or invariant a reader might miss). Be concise.\n\n"
        "Source (secrets redacted):\n"
        "```\n"
        f"{file_content}\n"
        "```"
    )


class AIProvider:
    """Base class. ``NotImplementedError`` di ``generate_summary`` sudah cukup
    sebagai kontrak — tidak perlu :mod:`abc`.
    """

    model: str = ""
    name: str = ""

    def generate_summary(self, file_content: str, function_context: dict) -> dict:
        raise NotImplementedError


class AnthropicProvider(AIProvider):
    model = "claude-haiku-4-5-20251001"
    name = "anthropic"

    def generate_summary(self, file_content: str, function_context: dict) -> dict:
        # ponytail: lazy import — SDK adalah optional extra (BLUEPRINT Phase 1).
        try:
            import anthropic
        except ImportError:
            raise AIError("sdk_not_installed")

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise AIError("auth_failed")

        scrubbed = scrub_secrets(file_content)
        prompt = _build_prompt(scrubbed, function_context)

        try:
            client = anthropic.Anthropic(api_key=key, timeout=30.0)
            resp = client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
        except anthropic.AuthenticationError as e:
            logger.warning(type(e).__name__)
            raise AIError("auth_failed")
        except anthropic.RateLimitError as e:
            logger.warning(type(e).__name__)
            retry_after = None
            # Header retry-after bisa ada di response.headers, optional.
            resp_obj = getattr(e, "response", None)
            if resp_obj is not None:
                headers = getattr(resp_obj, "headers", {}) or {}
                raw = headers.get("retry-after") or headers.get("Retry-After")
                if raw:
                    try:
                        retry_after = int(float(raw))
                    except (TypeError, ValueError):
                        retry_after = None
            raise AIError("rate_limited", retry_after=retry_after)
        except anthropic.APITimeoutError as e:
            logger.warning(type(e).__name__)
            raise AIError("timeout")
        except Exception as e:
            logger.warning(type(e).__name__)
            raise AIError("unknown")

        return _parse_summary(text)


class OpenAIProvider(AIProvider):
    model = "gpt-4o-mini"
    name = "openai"

    def generate_summary(self, file_content: str, function_context: dict) -> dict:
        # ponytail: lazy import — SDK adalah optional extra.
        try:
            import openai
            from openai import OpenAI
        except ImportError:
            raise AIError("sdk_not_installed")

        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise AIError("auth_failed")

        scrubbed = scrub_secrets(file_content)
        prompt = _build_prompt(scrubbed, function_context)

        try:
            client = OpenAI(api_key=key, timeout=30.0)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content
        except openai.AuthenticationError as e:
            logger.warning(type(e).__name__)
            raise AIError("auth_failed")
        except openai.RateLimitError as e:
            logger.warning(type(e).__name__)
            retry_after = None
            resp_obj = getattr(e, "response", None)
            if resp_obj is not None:
                headers = getattr(resp_obj, "headers", {}) or {}
                raw = headers.get("retry-after") or headers.get("Retry-After")
                if raw:
                    try:
                        retry_after = int(float(raw))
                    except (TypeError, ValueError):
                        retry_after = None
            raise AIError("rate_limited", retry_after=retry_after)
        except openai.APITimeoutError as e:
            logger.warning(type(e).__name__)
            raise AIError("timeout")
        except Exception as e:
            logger.warning(type(e).__name__)
            raise AIError("unknown")

        return _parse_summary(text)


def _parse_summary(text: str) -> dict:
    """Parse JSON string ke dict tiga-field. Raise ``AIError("parse_failed")``
    kalau bukan JSON valid."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise AIError("parse_failed")
    if not isinstance(data, dict):
        raise AIError("parse_failed")
    # ponytail: tidak validasi tipe per-field. Kalau model balas integer untuk
    # `role`, caller masih dapat dict — tambahkan validasi kalau ada bug nyata.
    return {
        "role": data.get("role", ""),
        "importance": data.get("importance", ""),
        "hidden_assumption": data.get("hidden_assumption", ""),
    }


def get_provider() -> "AIProvider | None":
    """Pilih provider berdasarkan env var. Anthropic dulu, OpenAI fallback."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIProvider()
    return None


if __name__ == "__main__":
    # Self-check: hanya logika murni (scrub + dispatch). Tidak panggil SDK.
    saved = {
        "ANTHROPIC_API_KEY": os.environ.pop("ANTHROPIC_API_KEY", None),
        "OPENAI_API_KEY": os.environ.pop("OPENAI_API_KEY", None),
    }
    try:
        # 1. password assignment di-redact.
        s1 = scrub_secrets("password = 'hunter2'")
        assert "[REDACTED]" in s1, s1
        assert "hunter2" not in s1, s1

        # 2. api_key assignment di-redact.
        s2 = scrub_secrets("api_key='sk-ant-abc'")
        assert "[REDACTED]" in s2, s2
        assert "sk-ant-abc" not in s2, s2

        # 3. Kode biasa tidak tersentuh.
        s3 = scrub_secrets("x = 1\ny = 2")
        assert s3 == "x = 1\ny = 2", s3

        # 4. Env kosong -> None.
        assert get_provider() is None

        # 5. Hanya ANTHROPIC_API_KEY -> AnthropicProvider, no api_key attr.
        os.environ["ANTHROPIC_API_KEY"] = "dummy"
        p = get_provider()
        assert isinstance(p, AnthropicProvider)
        assert not hasattr(p, "api_key")
        del os.environ["ANTHROPIC_API_KEY"]

        # 6. Hanya OPENAI_API_KEY -> OpenAIProvider.
        os.environ["OPENAI_API_KEY"] = "dummy"
        p = get_provider()
        assert isinstance(p, OpenAIProvider)
        del os.environ["OPENAI_API_KEY"]

        # 7. AIError membawa error_type.
        assert AIError("auth_failed").error_type == "auth_failed"
        assert AIError("rate_limited", retry_after=5).retry_after == 5

        print("provider.py self-check OK")
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
