from datetime import date

from backend.app.models.schemas import Activity, DayPlan, Itinerary
from backend.app.services.image_enrichment import ImageEnrichmentService


def make_itinerary() -> Itinerary:
    return Itinerary(
        destination="杭州", start_date=date(2026, 10, 1), end_date=date(2026, 10, 3),
        summary="测试行程", days=[
            DayPlan(date=date(2026, 10, 1), title="景点", activities=[
                Activity(time="09:00", name="西湖", description="景点", estimated_cost=0, poi_category="spot"),
                Activity(time="12:00", name="午餐", description="餐饮", estimated_cost=0, poi_category="meal"),
                Activity(time="15:00", name="灵隐寺", description="寺庙景点", estimated_cost=0),
            ]),
            DayPlan(date=date(2026, 10, 2), title="第二天", activities=[]),
            DayPlan(date=date(2026, 10, 3), title="第三天", activities=[]),
        ], total_estimated_cost=0,
    )


class StubAmap:
    def __init__(self, photos: dict[str, str | None] | None = None) -> None:
        self.photos = photos or {}
        self.poi_ids: list[str] = []

    def get_poi_photo(self, poi_id: str) -> str | None:
        self.poi_ids.append(poi_id)
        return self.photos.get(poi_id, f"https://webapi.amap.com/photo/{poi_id}.jpg")

    def get_poi_photos(self, poi_id: str) -> list[str]:
        photo = self.get_poi_photo(poi_id)
        return [photo] if photo else []


def test_enrichment_uses_verified_poi_ids_and_caches_results() -> None:
    client = StubAmap({"xihu": "https://webapi.amap.com/photo/xihu.jpg", "lingyin": "https://webapi.amap.com/photo/lingyin.jpg"})
    itinerary = make_itinerary()
    itinerary.days[0].activities[0].poi_id = "xihu"
    itinerary.days[0].activities[2].poi_id = "lingyin"
    service = ImageEnrichmentService(client)  # type: ignore[arg-type]
    service.enrich(itinerary)
    service.enrich(itinerary)
    assert client.poi_ids == ["xihu", "lingyin"]
    assert itinerary.days[0].activities[0].image_url == "https://webapi.amap.com/photo/xihu.jpg"
    assert itinerary.days[0].activities[1].image_url is None
    assert itinerary.days[0].activities[2].image_url == "https://webapi.amap.com/photo/lingyin.jpg"


def test_enrichment_leaves_missing_amap_photo_empty() -> None:
    itinerary = make_itinerary()
    itinerary.days[0].activities[0].poi_id = "xihu"
    ImageEnrichmentService(StubAmap({"xihu": None})).enrich(itinerary)  # type: ignore[arg-type]
    assert itinerary.days[0].activities[0].image_url is None


def test_enrichment_requires_verified_poi_id() -> None:
    itinerary = make_itinerary()
    ImageEnrichmentService(StubAmap()).enrich(itinerary)  # type: ignore[arg-type]
    assert itinerary.days[0].activities[0].image_url is None
