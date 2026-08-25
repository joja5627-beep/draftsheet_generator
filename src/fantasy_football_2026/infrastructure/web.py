"""Shared HTTP client with deterministic cache and offline semantics."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fantasy_football_2026.constants import HTTP_USER_AGENT, JSON_USER_AGENT
from fantasy_football_2026.errors import ContextError, StorageError
from fantasy_football_2026.infrastructure.storage import DEFAULT_STORE, ArtifactStore

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Runtime rules controlling cache reuse and network access."""

    refresh: bool
    offline: bool
    timeout: float
    current_day_only: bool = False
    stale_if_error: bool = False


@dataclass(frozen=True, slots=True)
class FetchResult(Generic[T]):
    """Fetched payload plus provenance used by generated audits."""

    payload: T
    retrieved_at: str
    from_cache: bool
    url: str


class CachedWebClient:
    """Fetch text, JSON, or binary data behind one cache lifecycle."""

    def __init__(
        self,
        policy: CachePolicy,
        *,
        store: ArtifactStore = DEFAULT_STORE,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self.store = store
        self._now = now or (lambda: datetime.now(UTC))

    def fetch_text(
        self,
        *,
        name: str,
        url: str,
        cache_path: Path,
        accept: str = "text/html,application/xhtml+xml",
        user_agent: str = HTTP_USER_AGENT,
    ) -> FetchResult[str]:
        return self._fetch(
            name=name,
            url=url,
            cache_path=cache_path,
            accept=accept,
            user_agent=user_agent,
            decode=lambda content: content.decode("utf-8"),
            encode=lambda payload: payload.encode("utf-8"),
        )

    def fetch_json(
        self,
        *,
        name: str,
        url: str,
        cache_path: Path,
    ) -> FetchResult[Any]:
        return self._fetch(
            name=name,
            url=url,
            cache_path=cache_path,
            accept="application/json",
            user_agent=JSON_USER_AGENT,
            decode=lambda content: json.loads(content.decode("utf-8")),
            encode=lambda payload: (
                json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            ),
        )

    def fetch_bytes(
        self,
        *,
        name: str,
        url: str,
        cache_path: Path,
        accept: str,
        validator: Callable[[bytes], bool] | None = None,
    ) -> FetchResult[bytes]:
        return self._fetch(
            name=name,
            url=url,
            cache_path=cache_path,
            accept=accept,
            user_agent=HTTP_USER_AGENT,
            decode=lambda content: content,
            encode=lambda payload: payload,
            validator=validator,
        )

    def _fetch(
        self,
        *,
        name: str,
        url: str,
        cache_path: Path,
        accept: str,
        user_agent: str,
        decode: Callable[[bytes], T],
        encode: Callable[[T], bytes],
        validator: Callable[[T], bool] | None = None,
    ) -> FetchResult[T]:
        now = self._now()
        try:
            cached = self._read_cache(cache_path, url=url, decode=decode)
        except StorageError:
            if self.policy.offline:
                raise
            cached = None
        if cached and validator is not None and not validator(cached.payload):
            if self.policy.offline:
                raise ContextError(f"Invalid cached payload for {name}: {cache_path}")
            cached = None
        if cached and self._cache_is_usable(cache_path, now):
            return cached
        if self.policy.offline:
            raise ContextError(f"Offline cache is missing: {cache_path}")

        request = Request(url, headers={"Accept": accept, "User-Agent": user_agent})
        try:
            with urlopen(request, timeout=self.policy.timeout) as response:  # noqa: S310
                payload = decode(response.read())
        except (
            HTTPError,
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ConnectionError,
        ) as error:
            if cached and self.policy.stale_if_error:
                return cached
            raise ContextError(f"Could not refresh {name} from {url}: {error}") from error

        if validator is not None and not validator(payload):
            raise ContextError(f"Invalid payload returned for {name} from {url}")
        self.store.write_bytes(cache_path, encode(payload))
        return FetchResult(
            payload=payload,
            retrieved_at=now.isoformat(timespec="seconds"),
            from_cache=False,
            url=url,
        )

    def _cache_is_usable(self, cache_path: Path, now: datetime) -> bool:
        if not cache_path.is_file():
            return False
        if self.policy.offline:
            return True
        if self.policy.refresh:
            return False
        if not self.policy.current_day_only:
            return True
        modified = datetime.fromtimestamp(cache_path.stat().st_mtime, UTC)
        return modified.date() == now.date()

    @staticmethod
    def _read_cache(
        cache_path: Path,
        *,
        url: str,
        decode: Callable[[bytes], T],
    ) -> FetchResult[T] | None:
        if not cache_path.is_file():
            return None
        try:
            payload = decode(cache_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StorageError(f"Could not decode cache {cache_path}: {error}") from error
        retrieved_at = datetime.fromtimestamp(cache_path.stat().st_mtime, UTC).isoformat(
            timespec="seconds"
        )
        return FetchResult(payload, retrieved_at, True, url)
