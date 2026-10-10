"""SQLite persistence for bounded trip editing sessions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from uuid import uuid4

from backend.app.models.schemas import SessionConstraints, SessionTurn, TripSession

from .errors import SessionNotFoundError, SessionVersionConflictError


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat()


class SQLiteSessionRepository:
    """Store session metadata in the same SQLite database as trip versions."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        ttl_seconds: int = 7 * 24 * 60 * 60,
        recent_turn_limit: int = 5,
        summary_max_length: int = 2000,
    ) -> None:
        if ttl_seconds <= 0 or recent_turn_limit <= 0 or summary_max_length <= 0:
            raise ValueError("session limits must be positive")
        self.database_path = str(database_path)
        self.ttl_seconds = ttl_seconds
        self.recent_turn_limit = recent_turn_limit
        self.summary_max_length = summary_max_length
        self._lock = RLock()
        self._memory_connection: sqlite3.Connection | None = None
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._memory_connection
            owns_connection = connection is None
            if owns_connection:
                connection = sqlite3.connect(self.database_path)
                connection.row_factory = sqlite3.Row
            assert connection is not None
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                if owns_connection:
                    connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trip_sessions (
                    session_id TEXT PRIMARY KEY,
                    trip_id TEXT NOT NULL,
                    current_version INTEGER NOT NULL CHECK (current_version >= 1),
                    initial_version INTEGER NOT NULL CHECK (initial_version >= 1),
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    summary TEXT NOT NULL DEFAULT '',
                    recent_turns TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trip_sessions_trip_id
                    ON trip_sessions (trip_id);
                CREATE INDEX IF NOT EXISTS idx_trip_sessions_expires_at
                    ON trip_sessions (expires_at);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(trip_sessions)").fetchall()
            }
            if "constraints_json" not in columns:
                connection.execute(
                    "ALTER TABLE trip_sessions ADD COLUMN constraints_json TEXT NOT NULL DEFAULT '{}'"
                )

    def _decode(self, row: sqlite3.Row) -> TripSession:
        return TripSession(
            session_id=row["session_id"],
            trip_id=row["trip_id"],
            current_version=row["current_version"],
            initial_version=row["initial_version"],
            constraints=SessionConstraints.model_validate(json.loads(row["constraints_json"])),
            summary=row["summary"],
            recent_turns=[
                SessionTurn.model_validate(item) for item in json.loads(row["recent_turns"])
            ],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
        )

    def create(
        self, trip_id: str, version: int, constraints: SessionConstraints | None = None
    ) -> TripSession:
        now = _now()
        session = TripSession(
            session_id=f"sess_{uuid4().hex}",
            trip_id=trip_id,
            current_version=version,
            initial_version=version,
            constraints=constraints or SessionConstraints(),
            created_at=_timestamp(now),
            updated_at=_timestamp(now),
            expires_at=_timestamp(now + timedelta(seconds=self.ttl_seconds)),
        )
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO trip_sessions
                (session_id, trip_id, current_version, initial_version, summary,
                 constraints_json, recent_turns, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.trip_id,
                    session.current_version,
                    session.initial_version,
                    session.summary,
                    json.dumps(session.constraints.model_dump(mode="json"), ensure_ascii=False),
                    "[]",
                    session.created_at,
                    session.updated_at,
                    session.expires_at,
                ),
            )
        return session

    def get(self, session_id: str) -> TripSession:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM trip_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise SessionNotFoundError(session_id)
        return self._decode(row)

    def update_after_edit(
        self,
        session_id: str,
        *,
        expected_version: int,
        result_version: int,
        turn: SessionTurn,
        summary: str,
    ) -> TripSession:
        current = self.get(session_id)
        turns = [*current.recent_turns, turn][-self.recent_turn_limit :]
        now = _now()
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE trip_sessions
                SET current_version = ?, summary = ?, recent_turns = ?,
                    updated_at = ?, expires_at = ?
                WHERE session_id = ? AND current_version = ?
                """,
                (
                    result_version,
                    summary[: self.summary_max_length],
                    json.dumps(
                        [item.model_dump(mode="json") for item in turns], ensure_ascii=False
                    ),
                    _timestamp(now),
                    _timestamp(expires_at),
                    session_id,
                    expected_version,
                ),
            )
            if result.rowcount != 1:
                raise SessionVersionConflictError(session_id)
        return self.get(session_id)

    def delete(self, session_id: str) -> None:
        with self._connection() as connection:
            result = connection.execute(
                "DELETE FROM trip_sessions WHERE session_id = ?", (session_id,)
            )
        if result.rowcount != 1:
            raise SessionNotFoundError(session_id)
