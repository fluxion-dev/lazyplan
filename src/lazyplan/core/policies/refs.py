"""External reference rules: URLs, providers, and kinds."""

from __future__ import annotations

from urllib.parse import urlsplit

REF_KINDS = ("epic", "issue", "doc", "other")


def validate_url(text: str) -> str:
    """Trim and validate an http(s) URL without credentials."""
    raw = str(text).strip()
    if not raw:
        raise ValueError("reference URL must not be empty")
    if any(ord(char) < 32 for char in raw):
        raise ValueError("reference URL must not contain control characters")
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("reference URL must start with http:// or https://")
    if parts.username or parts.password:
        raise ValueError("reference URL must not contain credentials")
    return raw


def infer_provider(url: str) -> str:
    """Map a URL host to a known provider name."""
    host = urlsplit(url).hostname or ""
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    if host == "linear.app" or host.endswith(".linear.app"):
        return "linear"
    if host.endswith(".atlassian.net"):
        return "jira"
    return "other"


def validate_kind(kind: str) -> str:
    """One of epic, issue, doc, or other."""
    clean = str(kind).strip().lower() or "issue"
    if clean not in REF_KINDS:
        raise ValueError(f"reference kind must be one of {', '.join(REF_KINDS)}")
    return clean


def external_id_from_url(url: str) -> str:
    """Last non-empty path segment, used when no id is supplied."""
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else ""


def normalize_ref(
    url: str,
    provider: str = "",
    kind: str = "issue",
    external_id: str = "",
) -> dict:
    """Validated reference fields with defaults applied."""
    clean_url = validate_url(url)
    return {
        "url": clean_url,
        "provider": (provider.strip().lower() or infer_provider(clean_url)),
        "kind": validate_kind(kind),
        "external_id": external_id.strip() or external_id_from_url(clean_url),
    }
