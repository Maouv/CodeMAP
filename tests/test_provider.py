"""Tests untuk ``scrub_secrets()`` — detect-secrets plugins + regex fallback.

Mengikuti PHASE3.md Task 1: layer-1 detect-secrets plugins sebagai detector
utama, layer-2 regex ``_SENSITIVE_PATTERNS`` sebagai defense-in-depth fallback.
"""

from graps.ai.provider import scrub_secrets


def test_scrub_secrets__detects_aws_key():
    # AKIA... adalah format AWS access key yang dikenali detect-secrets AWSKeyDetector.
    # Regex lama tidak punya keyword "aws_key" — ini validasi layer-1 plugin.
    source = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
    result = scrub_secrets(source)
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "[REDACTED]" in result


def test_scrub_secrets__detects_github_token():
    source = 'token = "ghp_1234567890abcdef1234567890abcdef1234"'
    result = scrub_secrets(source)
    assert "ghp_" not in result


def test_scrub_secrets__keeps_normal_code_intact():
    source = "def get_user(user_id: int) -> User:\n    return db.query(user_id)"
    result = scrub_secrets(source)
    assert result == source  # tidak ada false positive di kode normal


def test_scrub_secrets__regex_fallback_still_works():
    # Pattern lama (password = "...") tetap kena meski bukan format yang
    # dikenali detect-secrets plugin manapun.
    source = 'password = "hardcoded123"'
    result = scrub_secrets(source)
    assert "hardcoded123" not in result
