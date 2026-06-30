"""
graps/scanner/sanitize.py
Sanitize constant values before they enter the graph JSON.
Called by graph_builder.py before populating constants[].
"""

import re

# --- Name-based detection ---
# If the variable name contains any of these keywords, redact the value.
SENSITIVE_NAME_KEYWORDS = {
    "password", "passwd", "pwd",
    "secret", "token",
    "api_key", "apikey", "api_secret",
    "auth", "credential", "credentials",
    "private_key", "privkey",
    "access_key", "access_secret",
    "client_secret", "client_id",
    "signing_key", "encryption_key",
    "webhook_secret", "jwt_secret",
    "db_pass", "database_pass",
}

# --- Value-based detection (regex) ---
# Catches common credential patterns regardless of variable name.
SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"),          # Anthropic API key
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),                  # OpenAI API key
    re.compile(r"(?i)(postgres|mysql|mongodb|redis)://[^\s]+@"),  # DB connection string with credentials
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9\-_.]{20,}"),   # Bearer token
    re.compile(r"(?i)basic\s+[a-zA-Z0-9+/=]{20,}"),     # Basic auth
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),                  # GitHub personal access token
    re.compile(r"whsec_[a-zA-Z0-9]{32,}"),               # Stripe webhook secret
    re.compile(r"xoxb-[0-9]+-[a-zA-Z0-9\-]+"),          # Slack bot token
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"), # PEM private key
]


def sanitize_constant_value(name: str, value: str) -> str:
    """
    Returns '[REDACTED]' if the constant name or value looks like a credential.
    Otherwise returns the original value unchanged.

    Args:
        name:  Variable name as a string (e.g. 'DB_PASSWORD', 'MAX_RETRY')
        value: Literal value as a string (e.g. 'secret123', '3')

    Returns:
        Original value, or '[REDACTED]' if detected as sensitive.

    Examples:
        >>> sanitize_constant_value("MAX_RETRY", "3")
        '3'
        >>> sanitize_constant_value("DB_PASSWORD", "hunter2")
        '[REDACTED]'
        >>> sanitize_constant_value("API_URL", "sk-ant-abc123xyz4567890abcdef")
        '[REDACTED]'
        >>> sanitize_constant_value("WEBHOOK_SECRET", "whsec_abc123")
        '[REDACTED]'
    """
    name_lower = name.lower()

    # Check name-based keywords
    if any(keyword in name_lower for keyword in SENSITIVE_NAME_KEYWORDS):
        return "[REDACTED]"

    # Check value-based patterns
    for pattern in SENSITIVE_VALUE_PATTERNS:
        if pattern.search(value):
            return "[REDACTED]"

    return value
