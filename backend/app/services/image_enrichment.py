"""Attach official Amap POI images to spot activities."""

from __future__ import annotations

import logging
import re

from backend.app.integrations.amap_client import AmapClient
from backend.app.integrations.errors import MapServiceError
from backend.app.models.schemas import DayPlan, Itinerary

logger = logging.getLogger(__name__)

_NON_SPOT_PATTERN = re.compile(
    r"酒店|宾馆|旅馆|民宿|客栈|住宿|入住|餐厅|饭店|酒楼|酒家|大牌档|大排档|档口|"
    r"餐饮|用餐|就餐|早餐|午餐|晚餐|夜宵|小吃|简餐|美食|菜品|吃饭|品尝|餐食|食客|"
    r"restaurant|hotel|宿泊|dining|meal|food",
    re.IGNORECASE,
)


class ImageEnrichmentService:
    def __init__(self, client: AmapClient) -> None:
        self.client = client
        self._cache: dict[str, tuple[str, ...]] = {}

    def enrich(self, itinerary: Itinerary) -> Itinerary:
        used_urls = {
            activity.image_url
            for day in itinerary.days
            for activity in day.activities
            if activity.image_url
        }
        for day in itinerary.days:
            self.enrich_day(day, used_urls=used_urls)
        return itinerary

    def enrich_day(self, day: DayPlan, *, used_urls: set[str] | None = None) -> None:
        used_urls = used_urls if used_urls is not None else set()
        used_urls.update(activity.image_url for activity in day.activities if activity.image_url)
        for activity in day.activities:
            if not self._is_spot(activity) or activity.image_url:
                continue
            activity.image_url = self._find_image(activity.poi_id, used_urls)
            if activity.image_url:
                used_urls.add(activity.image_url)

    @staticmethod
    def _is_spot(activity: object) -> bool:
        category = getattr(activity, "poi_category", None)
        if category in {"meal", "hotel"}:
            return False
        if category == "spot":
            return True
        text = " ".join(
            str(getattr(activity, field, "") or "")
            for field in ("name", "description", "location", "address")
        )
        return not _NON_SPOT_PATTERN.search(text)

    def _find_image(self, poi_id: str | None, used_urls: set[str]) -> str | None:
        """Resolve an image only from the verified Amap POI identity."""
        if not poi_id:
            return None
        if poi_id in self._cache:
            return next((url for url in self._cache[poi_id] if url not in used_urls), None)
        try:
            urls = tuple(self.client.get_poi_photos(poi_id))
        except (MapServiceError, ValueError):
            logger.warning("Amap POI image lookup failed for %s", poi_id)
            urls = ()
        self._cache[poi_id] = urls
        return next((url for url in urls if url not in used_urls), None)
