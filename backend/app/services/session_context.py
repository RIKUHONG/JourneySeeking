"""Multi-turn context service for saved itinerary editing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.app.models.schemas import (
    SessionCreateRequest,
    SessionEditRequest,
    SessionEditResponse,
    SessionTurn,
    TripEditRequest,
    TripSession,
)
from backend.app.services.trip_edit import TripEditService
from backend.app.storage import SQLiteSessionRepository
from backend.app.storage.errors import SessionNotFoundError, SessionVersionConflictError


class SessionError(Exception):
    code = "SESSION_NOT_FOUND"
    message = "行程会话不存在"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message


class SessionExpiredError(SessionError):
    code = "SESSION_EXPIRED"
    message = "行程会话已过期"


class SessionTripMismatchError(SessionError):
    code = "SESSION_TRIP_MISMATCH"
    message = "会话与行程不匹配"


class SessionVersionError(SessionError):
    code = "SESSION_VERSION_CONFLICT"
    message = "会话引用的行程版本已发生变化，请重新开始编辑"


class SessionService:
    def __init__(
        self,
        session_repository: SQLiteSessionRepository,
        trip_repository: Any,
        trip_edit_service: TripEditService,
    ) -> None:
        self.sessions = session_repository
        self.trips = trip_repository
        self.editor = trip_edit_service

    def create(self, trip_id: str, request: SessionCreateRequest) -> TripSession:
        self.trips.get_version(trip_id, request.version)
        return self.sessions.create(trip_id, request.version, request.constraints)

    def get(self, trip_id: str, session_id: str) -> TripSession:
        session = self._load(trip_id, session_id)
        return session

    def delete(self, trip_id: str, session_id: str) -> None:
        self._load(trip_id, session_id)
        self.sessions.delete(session_id)

    def edit(
        self, trip_id: str, session_id: str, request: SessionEditRequest
    ) -> SessionEditResponse:
        session = self._load(trip_id, session_id)
        current = self.trips.get_current(trip_id)
        if current.version != session.current_version:
            raise SessionVersionError()

        context = [
            {
                "summary": session.summary,
                "constraints": session.constraints.model_dump(mode="json"),
                "recent_turns": [turn.model_dump(mode="json") for turn in session.recent_turns],
            }
        ]
        result = self.editor.edit(
            trip_id,
            TripEditRequest(
                expected_version=session.current_version,
                date=request.date,
                instruction=request.instruction,
            ),
            session_context=context,
        )
        turn = SessionTurn(
            turn_id=f"turn_{session_id}_{result.version}",
            instruction=request.instruction,
            target_date=request.date,
            base_version=session.current_version,
            result_version=result.version,
            status="succeeded",
            change_summary=result.change_summary,
            created_at=datetime.now(UTC).isoformat(),
        )
        summary = self._next_summary(session, request.instruction, result.change_summary)
        try:
            updated_session = self.sessions.update_after_edit(
                session_id,
                expected_version=session.current_version,
                result_version=result.version,
                turn=turn,
                summary=summary,
            )
        except SessionVersionConflictError as exc:
            raise SessionVersionError() from exc
        return SessionEditResponse(
            session_id=session_id,
            trip_id=trip_id,
            version=result.version,
            itinerary=result.itinerary,
            change_summary=result.change_summary,
            session=updated_session,
        )

    def _load(self, trip_id: str, session_id: str) -> TripSession:
        try:
            session = self.sessions.get(session_id)
        except SessionNotFoundError as exc:
            raise SessionError() from exc
        if session.trip_id != trip_id:
            raise SessionTripMismatchError()
        if self._expired(session.expires_at):
            raise SessionExpiredError()
        return session

    @staticmethod
    def _expired(expires_at: str) -> bool:
        return datetime.fromisoformat(expires_at).astimezone(UTC) <= datetime.now(UTC)

    @staticmethod
    def _next_summary(session: TripSession, instruction: str, change_summary: list[str]) -> str:
        fragments = [session.summary, f"用户要求：{instruction}", *change_summary]
        return "；".join(item for item in fragments if item)[:2000]
