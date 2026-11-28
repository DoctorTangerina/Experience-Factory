"""Secret scrubbing for Traces: credentials are replaced before a Trace segment is stored.

Scrubbing runs on the harness-neutral schema (ADR-0005), so it does not depend on any harness.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experience_factory.traces import JsonValue

REDACTED = "[REDACTED]"

# Names under which a credential is assigned or passed: `DATABASE_PASSWORD=...`, `"api_key": ...`.
# A name must end in one of these, so `max_tokens` or `token_count` is not taken for a secret.
_SECRET_NAME = r"(?:password|passwd|secret|api[_-]?key|access[_-]?key|private[_-]?key|token)"
_SECRET_KEY = re.compile(rf"(?i).*?{_SECRET_NAME}")

# Credentials recognisable by their own shape, wherever they appear.
_CREDENTIALS = re.compile(
    "|".join(
        (
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            r"\bsk-[A-Za-z0-9_-]{20,}",  # Anthropic and OpenAI API keys
            r"\bgh[pousr]_[A-Za-z0-9]{36,}",  # GitHub tokens
            r"\bgithub_pat_[A-Za-z0-9_]{22,}",  # GitHub fine-grained tokens
            r"\bglpat-[A-Za-z0-9_-]{20,}",  # GitLab tokens
            r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",  # AWS access key ids
            r"\bxox[abposr]-[A-Za-z0-9-]{10,}",  # Slack tokens
            r"\bAIza[0-9A-Za-z_-]{30,}",  # Google API keys
            r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}",  # Stripe keys
            r"\bnpm_[A-Za-z0-9]{36,}",  # npm tokens
            r"\bhf_[A-Za-z0-9]{30,}",  # Hugging Face tokens
            r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}",  # JSON Web Tokens
        )
    ),
    re.DOTALL,
)

# Credentials recognisable by what precedes them. Only the credential itself, the named group
# starting "secret", is replaced; what precedes it is kept.
_PRECEDED = (
    # Authorization headers: `Authorization: Bearer <token>`, `authorization="Basic <...>"`.
    re.compile(
        r"(?i)authorization[\"']?\s*[:=]\s*[\"']?(?:(?:bearer|basic|token|digest)\s+)?"
        r"(?P<secret>[^\s\"']+)"
    ),
    # Bearer tokens outside a header; a token is taken to contain a digit, to spare prose.
    re.compile(r"\bBearer\s+(?P<secret>(?=\S*\d)[A-Za-z0-9._~+/-]{8,}=*)"),
    # Passwords in URLs: `https://user:<password>@host`.
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?P<secret>[^\s@/]+)@"),
    # Assignments to a secret name: `NAME=<value>`, `name: "<value>"`.
    re.compile(
        rf"(?i)\b[\w.-]*?{_SECRET_NAME}\b[\"']?\s*[:=]\s*"
        r"(?:\"(?P<secret>[^\"]*)\"|'(?P<secret_sq>[^']*)'|(?P<secret_bare>[^\s\"',;&]+))"
    ),
)


def _redact_secret_groups(match: re.Match[str]) -> str:
    text, start = match.group(0), match.start()
    for name in ("secret", "secret_sq", "secret_bare"):
        if name in match.re.groupindex and match.group(name) is not None:
            begin, end = match.start(name) - start, match.end(name) - start
            return text[:begin] + REDACTED + text[end:]
    return text


def scrub_text(text: str) -> str:
    """`text` with every secret it contains replaced by a redaction marker."""
    text = _CREDENTIALS.sub(REDACTED, text)
    for pattern in _PRECEDED:
        text = pattern.sub(_redact_secret_groups, text)
    return text


def scrub_json(value: JsonValue) -> JsonValue:
    """`value` with every secret in its strings, keys included, replaced."""
    match value:
        case str():
            return scrub_text(value)
        case list():
            return [scrub_json(item) for item in value]
        case dict():
            return scrub_json_object(value)
        case _:
            return value


def scrub_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """The JSON object `value` with every secret in its keys and values replaced. A string held
    under a secret's name, such as `password` or `api_key`, is replaced whole."""
    return {
        scrub_text(key): (
            REDACTED if isinstance(item, str) and _SECRET_KEY.fullmatch(key) else scrub_json(item)
        )
        for key, item in value.items()
    }
