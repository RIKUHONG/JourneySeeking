"""Cache abstractions used by external-service integrations.

The interface is deliberately small and synchronous so it can be implemented by
an in-process cache today and by Redis (or another backend) later.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Cache(Protocol, Generic[T]):
    """A best-effort key/value cache.

    Implementations may raise a backend-specific exception. Callers should treat
    those failures as cache misses and continue without caching.
    """

    def get(self, key: str) -> T | None: ...

    def set(self, key: str, value: T, *, ttl_seconds: float | None = None) -> None: ...

    def delete(self, key: str) -> None: ...

    def clear(self) -> None: ...
