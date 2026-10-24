"""GitHub read client: ETag cache, rate limits, and redacted errors.

Stdlib only. No network call happens unless a caller invokes a method.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .forge import AuthStatus, RepoRef, redact, resolve_auth

if TYPE_CHECKING:
    from .store import Store

API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "lpui-github"
DEFAULT_TTL = 300
DEFAULT_TIMEOUT = 10.0


class GitHubError(Exception):
    """GitHub request failed; the message never contains a token."""


class GitHubRateLimit(GitHubError):
    """GitHub asked us to wait; reset_at/retry_after are best-effort."""

    def __init__(
        self,
        message: str,
        reset_at: int = 0,
        retry_after: int = 0,
    ) -> None:
        super().__init__(message)
        self.reset_at = reset_at
        self.retry_after = retry_after


@dataclass(frozen=True)
class FetchResult:
    """One GitHub response plus its cache state."""

    data: Any
    etag: str = ""
    from_cache: bool = False
    stale: bool = False
    status: int = 200


class GitHubClient:
    """Read-only GitHub client with a Store-backed ETag cache."""

    def __init__(
        self,
        auth: AuthStatus | None = None,
        store: Store | None = None,
        base_url: str = API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.auth = auth or resolve_auth()
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def pulls_for_commit(self, ref: RepoRef, sha: str, force: bool = False) -> FetchResult:
        """Pull requests that contain one commit."""
        path = f"/repos/{ref.owner}/{ref.repo}/commits/{sha}/pulls"
        return self.get_json(path, force=force)

    def pulls_for_branch(self, ref: RepoRef, branch: str, force: bool = False) -> FetchResult:
        """Every pull request whose head is one branch, open or closed."""
        head = urllib.parse.quote(f"{ref.owner}:{branch.strip()}", safe=":/")
        path = f"/repos/{ref.owner}/{ref.repo}/pulls?head={head}&state=all"
        return self.get_json(path, force=force)

    def pulls_for_merge(self, ref: RepoRef, sha: str, force: bool = False) -> FetchResult:
        """Pull requests associated with one merge commit."""
        return self.pulls_for_commit(ref, sha, force=force)

    def pull(self, ref: RepoRef, number: int, force: bool = False) -> FetchResult:
        """One pull request by number."""
        path = f"/repos/{ref.owner}/{ref.repo}/pulls/{number}"
        return self.get_json(path, force=force)

    def checks(self, ref: RepoRef, sha: str, force: bool = False) -> FetchResult:
        """Check runs for one commit."""
        path = f"/repos/{ref.owner}/{ref.repo}/commits/{sha}/check-runs"
        return self.get_json(path, force=force)

    def reviews(self, ref: RepoRef, number: int, force: bool = False) -> FetchResult:
        """Reviews for one pull request."""
        path = f"/repos/{ref.owner}/{ref.repo}/pulls/{number}/reviews"
        return self.get_json(path, force=force)

    def get_json(
        self,
        path: str,
        *,
        cache_key: str = "",
        force: bool = False,
        ttl: int = DEFAULT_TTL,
    ) -> FetchResult:
        """GET one API path, revalidating a cached body with an ETag."""
        key = cache_key or f"github:{path}"
        cached = self.store.cache_get(key) if self.store is not None else None
        cached_data = self._cached_data(cached)
        if (
            cached is not None
            and cached_data is not None
            and not force
            and self._fresh(cached, ttl)
        ):
            return FetchResult(
                data=cached_data,
                etag=str(cached.get("etag", "")),
                from_cache=True,
                status=200,
            )

        headers = self._request_headers(cached)
        etag = str(cached.get("etag", "")) if cached is not None else ""
        request = urllib.request.Request(f"{self.base_url}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return self._parse_response(response, key, etag)
        except urllib.error.HTTPError as exc:
            return self._handle_http_error(exc, key, cached, cached_data, etag)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return self._offline_or_raise(exc, cached, cached_data, etag)

    def _request_headers(self, cached: dict | None) -> dict[str, str]:
        """API headers plus conditional and auth fields."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }
        if self.auth.token:
            headers["Authorization"] = f"Bearer {self.auth.token}"
        etag = str(cached.get("etag", "")) if cached is not None else ""
        if etag:
            headers["If-None-Match"] = etag
        return headers

    def _parse_response(self, response: Any, key: str, etag: str) -> FetchResult:
        """Decode a 2xx body and cache it with its ETag."""
        body = response.read().decode("utf-8", "replace")
        new_etag = response.headers.get("ETag", "") or etag
        data = json.loads(body) if body else None
        if self.store is not None:
            self.store.cache_put(key, new_etag, int(time.time()), body)
        return FetchResult(data=data, etag=new_etag, status=response.status)

    def _handle_http_error(
        self,
        exc: urllib.error.HTTPError,
        key: str,
        cached: dict | None,
        cached_data: Any,
        etag: str,
    ) -> FetchResult:
        """304 revalidation, rate limits, stale fallback, or a typed error."""
        if exc.code == 304 and cached is not None:
            if self.store is not None:
                self.store.cache_put(key, etag, int(time.time()), str(cached.get("payload", "")))
            return FetchResult(data=cached_data, etag=etag, from_cache=True, status=304)
        if exc.code in (403, 429):
            raise self._rate_limit(exc) from exc
        if cached is not None:
            return self._stale(cached_data, etag)
        raise self._error(exc) from exc

    def _offline_or_raise(
        self,
        exc: Exception,
        cached: dict | None,
        cached_data: Any,
        etag: str,
    ) -> FetchResult:
        """Stale cache on network failure, else a typed redacted error."""
        if cached is not None:
            return self._stale(cached_data, etag)
        raise GitHubError(self._safe(f"GitHub request failed: {exc}")) from exc

    @staticmethod
    def _cached_data(cached: dict | None) -> Any:
        """Decode a cached body, or None when absent/invalid."""
        if cached is None:
            return None
        payload = str(cached.get("payload", "") or "")
        if not payload:
            return None
        try:
            return json.loads(payload)
        except ValueError:
            return None

    @staticmethod
    def _fresh(cached: dict, ttl: int) -> bool:
        """True when the cached body is younger than ttl."""
        try:
            fetched = int(cached.get("fetched_at", 0) or 0)
        except (TypeError, ValueError):
            fetched = 0
        return bool(fetched and int(time.time()) - fetched < ttl)

    @staticmethod
    def _stale(data: Any, etag: str) -> FetchResult:
        """Cached body used because the network failed."""
        return FetchResult(data=data, etag=etag, from_cache=True, stale=True, status=0)

    def _rate_limit(self, exc: urllib.error.HTTPError) -> GitHubRateLimit:
        """Typed rate-limit error with reset headers, token redacted."""
        headers: Any = exc.headers or {}
        remaining = str(headers.get("X-RateLimit-Remaining", "") or "")
        reset_at = self._int_header(headers, "X-RateLimit-Reset")
        retry_after = self._int_header(headers, "Retry-After")
        if exc.code == 403 and remaining not in ("0", "0.0", ""):
            return GitHubRateLimit(
                self._safe("GitHub refused the request (403)"), reset_at, retry_after
            )
        if reset_at:
            message = f"GitHub rate limit reached; resets at {reset_at}"
        elif retry_after:
            message = f"GitHub rate limit reached; retry after {retry_after}s"
        else:
            message = "GitHub rate limit reached"
        return GitHubRateLimit(self._safe(message), reset_at, retry_after)

    def _error(self, exc: urllib.error.HTTPError) -> GitHubError:
        """Typed HTTP error with the response body redacted and truncated."""
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except (OSError, ValueError):
            body = ""
        detail = f"GitHub request failed ({exc.code})"
        if body:
            detail = f"{detail}: {body[:300]}"
        return GitHubError(self._safe(detail))

    def _safe(self, text: str) -> str:
        """Redact the active token and token-shaped strings."""
        return redact(text, self.auth.token)

    @staticmethod
    def _int_header(headers: Any, name: str) -> int:
        """Integer header value, or 0."""
        try:
            return int(str(headers.get(name, "") or 0))
        except (TypeError, ValueError):
            return 0
