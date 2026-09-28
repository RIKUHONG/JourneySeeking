"""Thread-safe in-memory TTL cache."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float | None


class MemoryCache(Generic[T]):
    """A bounded-free in-process cache with optional per-entry TTL.

    ``None`` means no expiration. A non-positive TTL expires immediately. Values
    are intentionally not serialized; this keeps the implementation suitable for
    dataclass contracts and makes it a drop-in test adapter for Redis later.
    """

    def __init__(
        self,
        *,
        default_ttl_seconds: float | None = 300.0,
        ttl_seconds: float | None = None,
    ) -> None:
        if ttl_seconds is not None:
            if default_ttl_seconds != 300.0:
                raise ValueError("pass only one of ttl_seconds and default_ttl_seconds")
            default_ttl_seconds = ttl_seconds
        if default_ttl_seconds is not None and default_ttl_seconds < 0:
            raise ValueError("default_ttl_seconds cannot be negative")
        self.default_ttl_seconds = default_ttl_seconds
        self._entries: dict[str, _Entry[T]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> T | None:
        self._validate_key(key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at <= time.monotonic():
                del self._entries[key]
                return None
            return entry.value

    def set(self, key: str, value: T, *, ttl_seconds: float | None = None) -> None:
        self._validate_key(key)
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl is not None and ttl < 0:
            raise ValueError("ttl_seconds cannot be negative")
        expires_at = None if ttl is None else time.monotonic() + ttl
        with self._lock:
            self._entries[key] = _Entry(value, expires_at)

    def delete(self, key: str) -> None:
        self._validate_key(key)
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not key:
            raise ValueError("cache key must be a non-empty string")


InMemoryCache = MemoryCache
