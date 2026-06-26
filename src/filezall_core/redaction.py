from __future__ import annotations

import re


_VALUE_PATTERN = r"(?:'[^']*'|\"[^\"]*\"|[^\s,;]+)"

_SENSITIVE_PATTERNS = [
    re.compile(
        rf"(?i)\b(password|passphrase|token|secret|FILEZALL_AGENT_TOKEN|ssh_key_path|agent_token_ref)=({_VALUE_PATTERN})"
    ),
    re.compile(r"(?i)(Authorization:\s*Bearer\s+)([^\s,;]+)"),
]


def redact_sensitive(text: str) -> str:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


def _redact_match(match: re.Match[str]) -> str:
    key = match.group(1)
    if key.lower().startswith("authorization"):
        return f"{key}<redacted>"
    return f"{key}=<redacted>"
