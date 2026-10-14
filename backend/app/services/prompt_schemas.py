"""Model-owned output shapes used to describe prompts, not provider facts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.schemas import Activity, DayPlan, Money, NonEmptyText


class ActivityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    name: NonEmptyText
    description: str
    location: str | None = None
    duration_minutes: int | None = Field(default=None, strict=True, gt=0)
    estimated_cost: Money
    poi_id: str | None = None
    poi_category: Literal["spot", "meal", "hotel"] | None = None


class DayDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    title: NonEmptyText
    activities: list[ActivityDraft]


class ItineraryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: NonEmptyText
    start_date: date
    end_date: date
    summary: NonEmptyText
    days: list[DayDraft] = Field(min_length=1)
    total_estimated_cost: Money


class DayEditDraft(DayDraft):
    def as_day(self, current: DayPlan) -> DayPlan:
        return DayPlan(
            date=self.date,
            title=self.title,
            activities=[Activity.model_validate(item.model_dump()) for item in self.activities],
            weather=current.weather,
            weather_advice=current.weather_advice,
        )
