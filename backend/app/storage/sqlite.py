"""SQLite repository for complete, immutable itinerary versions."""

from __future__ import annotations

import json
import sqlite3
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.models.schemas import (
    Itinerary,
    TripListResponse,
    TripSummary,
    TripVersionsResponse,
    TripVersionSummary,
)

from .errors import InvalidTripCursorError, TripNotFoundError, TripVersionConflictError


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _encode_cursor(updated_at: str, trip_id: str) -> str:
    payload = json.dumps(
        {"updated_at": updated_at, "trip_id": trip_id},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(urlsafe_b64decode(cursor + padding).decode("utf-8"))
        updated_at = payload["updated_at"]
        trip_id = payload["trip_id"]
    except (Base64Error, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise InvalidTripCursorError() from exc
    if not isinstance(updated_at, str) or not updated_at:
        raise InvalidTripCursorError()
    if not isinstance(trip_id, str) or not trip_id:
        raise InvalidTripCursorError()
    return updated_at, trip_id


class SQLiteTripRepository:
    """Persist trips in SQLite using one short-lived connection per operation."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        if str(self.database_path) != ":memory:":
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS trips (
                    trip_id TEXT PRIMARY KEY,
                    current_version INTEGER NOT NULL CHECK (current_version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trip_versions (
                    trip_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version >= 1),
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (trip_id, version),
                    FOREIGN KEY (trip_id) REFERENCES trips(trip_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_trips_updated_at
                    ON trips (updated_at DESC, trip_id DESC);
                """
            )

    @staticmethod
    def _with_identity(itinerary: Itinerary, trip_id: str, version: int) -> Itinerary:
        payload = itinerary.model_dump(mode="json")
        payload.update(trip_id=trip_id, version=version)
        return Itinerary.model_validate(payload)

    @staticmethod
    def _decode(row: sqlite3.Row) -> Itinerary:
        return Itinerary.model_validate(json.loads(row["payload"]))

    def create(self, itinerary: Itinerary) -> Itinerary:
        trip_id = itinerary.trip_id or f"trip_{uuid4().hex}"
        stored = self._with_identity(itinerary, trip_id, 1)
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO trips (trip_id, current_version, created_at, updated_at) VALUES (?, 1, ?, ?)",
                (trip_id, timestamp, timestamp),
            )
            connection.execute(
                "INSERT INTO trip_versions (trip_id, version, payload, created_at) VALUES (?, 1, ?, ?)",
                (
                    trip_id,
                    json.dumps(stored.model_dump(mode="json"), ensure_ascii=False),
                    timestamp,
                ),
            )
        return stored

    def get_current(self, trip_id: str) -> Itinerary:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT v.payload
                FROM trips AS t
                JOIN trip_versions AS v
                  ON v.trip_id = t.trip_id AND v.version = t.current_version
                WHERE t.trip_id = ?
                """,
                (trip_id,),
            ).fetchone()
        if row is None:
            raise TripNotFoundError(trip_id)
        return self._decode(row)

    def get_version(self, trip_id: str, version: int) -> Itinerary:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM trip_versions WHERE trip_id = ? AND version = ?",
                (trip_id, version),
            ).fetchone()
        if row is None:
            raise TripNotFoundError(f"{trip_id}@{version}")
        return self._decode(row)

    def list(self, *, limit: int, cursor: str | None = None) -> TripListResponse:
        cursor_key = _decode_cursor(cursor) if cursor is not None else None
        with self._connect() as connection:
            if cursor_key is None:
                rows = connection.execute(
                    """
                    SELECT t.trip_id, t.current_version, t.updated_at, v.payload
                    FROM trips AS t
                    JOIN trip_versions AS v
                      ON v.trip_id = t.trip_id AND v.version = t.current_version
                    ORDER BY t.updated_at DESC, t.trip_id DESC
                    LIMIT ?
                    """,
                    (limit + 1,),
                ).fetchall()
            else:
                updated_at, trip_id = cursor_key
                rows = connection.execute(
                    """
                    SELECT t.trip_id, t.current_version, t.updated_at, v.payload
                    FROM trips AS t
                    JOIN trip_versions AS v
                      ON v.trip_id = t.trip_id AND v.version = t.current_version
                    WHERE t.updated_at < ? OR (t.updated_at = ? AND t.trip_id < ?)
                    ORDER BY t.updated_at DESC, t.trip_id DESC
                    LIMIT ?
                    """,
                    (updated_at, updated_at, trip_id, limit + 1),
                ).fetchall()
        has_more = len(rows) > limit
        items = [
            TripSummary(
                trip_id=row["trip_id"],
                version=row["current_version"],
                destination=(payload := json.loads(row["payload"]))["destination"],
                summary=payload["summary"],
                start_date=payload["start_date"],
                end_date=payload["end_date"],
            )
            for row in rows[:limit]
        ]
        next_cursor = (
            _encode_cursor(rows[limit - 1]["updated_at"], rows[limit - 1]["trip_id"])
            if has_more
            else None
        )
        return TripListResponse(items=items, next_cursor=next_cursor)

    def save_version(self, itinerary: Itinerary, *, expected_version: int) -> Itinerary:
        if itinerary.trip_id is None:
            raise ValueError("existing itinerary requires trip_id")
        with self._connect() as connection:
            timestamp = _now()
            result = connection.execute(
                """
                UPDATE trips
                SET current_version = current_version + 1, updated_at = ?
                WHERE trip_id = ? AND current_version = ?
                """,
                (timestamp, itinerary.trip_id, expected_version),
            )
            if result.rowcount != 1:
                exists = connection.execute(
                    "SELECT 1 FROM trips WHERE trip_id = ?", (itinerary.trip_id,)
                ).fetchone()
                if exists is None:
                    raise TripNotFoundError(itinerary.trip_id)
                raise TripVersionConflictError(itinerary.trip_id)
            new_version = expected_version + 1
            stored = self._with_identity(itinerary, itinerary.trip_id, new_version)
            connection.execute(
                "INSERT INTO trip_versions (trip_id, version, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    itinerary.trip_id,
                    new_version,
                    json.dumps(stored.model_dump(mode="json"), ensure_ascii=False),
                    timestamp,
                ),
            )
        return stored

    def list_versions(self, trip_id: str) -> TripVersionsResponse:
        with self._connect() as connection:
            trip = connection.execute(
                "SELECT current_version FROM trips WHERE trip_id = ?", (trip_id,)
            ).fetchone()
            if trip is None:
                raise TripNotFoundError(trip_id)
            rows = connection.execute(
                """
                SELECT trip_id, version, created_at, payload
                FROM trip_versions WHERE trip_id = ? ORDER BY version DESC
                """,
                (trip_id,),
            ).fetchall()
        return TripVersionsResponse(
            trip_id=trip_id,
            current_version=trip["current_version"],
            items=[
                TripVersionSummary(
                    trip_id=row["trip_id"],
                    version=row["version"],
                    created_at=row["created_at"],
                    summary=json.loads(row["payload"])["summary"],
                )
                for row in rows
            ],
        )

    def delete(self, trip_id: str) -> None:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM trips WHERE trip_id = ?", (trip_id,))
        if result.rowcount != 1:
            raise TripNotFoundError(trip_id)
