"""Deterministic destination normalization and coverage classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CityCoverageStatus(StrEnum):
    """How confidently the destination can be used for city-scoped planning."""

    CURATED = "curated"
    DYNAMIC = "dynamic"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class CityResolution:
    """Canonical destination text and the reason it is eligible or ineligible."""

    requested: str
    city: str
    status: CityCoverageStatus
    reason: str


_ALIASES = {
    "北京": "北京",
    "北京市": "北京",
    "杭州": "杭州",
    "杭州市": "杭州",
    "西湖": "杭州",
    "西湖区": "杭州",
    "成都": "成都",
    "成都市": "成都",
    "大理": "大理",
    "大理市": "大理",
    "厦门": "厦门",
    "厦门市": "厦门",
    "三亚": "三亚",
    "三亚市": "三亚",
    "西安": "西安",
    "西安市": "西安",
}

_PROVINCES = {
    "安徽",
    "福建",
    "甘肃",
    "广东",
    "广西",
    "贵州",
    "海南",
    "河北",
    "河南",
    "黑龙江",
    "湖北",
    "湖南",
    "吉林",
    "江苏",
    "江西",
    "辽宁",
    "内蒙古",
    "宁夏",
    "青海",
    "山东",
    "山西",
    "陕西",
    "四川",
    "西藏",
    "新疆",
    "云南",
    "浙江",
}


def _key(value: str) -> str:
    return re.sub(r"[\s,，。·]+", "", value).removesuffix("省").removesuffix("市")


def resolve_city(destination: str) -> CityResolution:
    """Normalize a destination without making a network request.

    Unknown non-province destinations remain dynamic. Province-level input is
    intentionally ineligible because a city-scoped candidate pool cannot be
    trusted for it.
    """

    requested = destination.strip()
    if not requested:
        return CityResolution("", "", CityCoverageStatus.INSUFFICIENT_DATA, "empty_destination")

    alias = _ALIASES.get(requested) or _ALIASES.get(_key(requested))
    if alias is not None:
        status = (
            CityCoverageStatus.CURATED
            if alias in {"北京", "杭州", "成都", "大理", "厦门", "三亚", "西安"}
            else CityCoverageStatus.DYNAMIC
        )
        return CityResolution(requested, alias, status, "alias_normalized")

    if _key(requested) in {_key(item) for item in _PROVINCES}:
        return CityResolution(
            requested,
            requested.removesuffix("省"),
            CityCoverageStatus.INSUFFICIENT_DATA,
            "province_requires_city",
        )

    return CityResolution(requested, requested, CityCoverageStatus.DYNAMIC, "unregistered_city")
