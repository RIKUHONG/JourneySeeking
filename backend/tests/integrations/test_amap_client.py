import httpx
import pytest

from backend.app.config.settings import Settings
from backend.app.integrations.amap_client import AmapClient
from backend.app.integrations.contracts import Coordinates
from backend.app.integrations.errors import FailureReason, MapServiceError


@pytest.fixture
def config():
    return Settings(
        amap_api_key="test-key", amap_base_url="https://amap.test/v3", amap_max_retries=1
    )


def client(config, handler):
    return AmapClient(config, httpx.Client(transport=httpx.MockTransport(handler)))


def test_search_pois_maps_reference_project_fields(config):
    def handler(request):
        assert request.url.path == "/v3/place/text"
        assert request.url.params["key"] == "test-key"
        assert request.url.params["keywords"] == "西湖"
        assert request.url.params["city"] == "杭州"
        assert request.url.params["citylimit"] == "true"
        assert request.url.params["offset"] == "5"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "pois": [
                    {
                        "id": "poi1",
                        "name": "西湖",
                        "address": "杭州西湖区",
                        "location": "120.1,30.2",
                    }
                ],
            },
        )

    places = client(config, handler).search_pois("西湖", city="杭州", limit=5)

    assert places[0].provider_id == "poi1"
    assert places[0].coordinates == Coordinates(120.1, 30.2)


def test_plan_route_uses_amap_driving_fields(config):
    def handler(request):
        assert request.url.path == "/v3/direction/driving"
        assert request.url.params["origin"] == "120.1,30.2"
        assert request.url.params["destination"] == "120.2,30.3"
        return httpx.Response(
            200, json={"status": "1", "route": {"paths": [{"distance": "2500", "duration": "600"}]}}
        )

    route = client(config, handler).plan_route(Coordinates(120.1, 30.2), Coordinates(120.2, 30.3))

    assert (route.distance_meters, route.duration_seconds) == (2500, 600)


def test_walking_route_uses_walking_endpoint(config):
    def handler(request):
        assert request.url.path == "/v3/direction/walking"
        assert "strategy" not in request.url.params
        return httpx.Response(
            200, json={"status": "1", "route": {"paths": [{"distance": "800", "duration": "540"}]}}
        )

    route = client(config, handler).plan_route(
        Coordinates(120.1, 30.2), Coordinates(120.2, 30.3), mode="walking"
    )

    assert route.distance_meters == 800


def test_missing_route_is_invalid_response(config):
    with pytest.raises(MapServiceError) as exc_info:
        client(
            config,
            lambda request: httpx.Response(200, json={"status": "1", "route": {"paths": []}}),
        ).plan_route(Coordinates(120.1, 30.2), Coordinates(120.2, 30.3))

    assert exc_info.value.reason is FailureReason.INVALID_RESPONSE


def test_retries_transient_status_then_succeeds(config, monkeypatch):
    statuses = iter([503, 200])
    calls = []
    monkeypatch.setattr("backend.app.integrations._amap_http.time.sleep", calls.append)

    def handler(request):
        status = next(statuses)
        return httpx.Response(status, json={"status": "1", "pois": []})

    assert client(config, handler).search_pois("西湖") == []
    assert calls == [1]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(200, json={"status": "0", "info": "secret"}), FailureReason.PROVIDER),
        (httpx.Response(200, json={"status": "1"}), FailureReason.INVALID_RESPONSE),
        (httpx.Response(200, text="not-json"), FailureReason.INVALID_RESPONSE),
        (httpx.Response(401, text="secret"), FailureReason.PROVIDER),
    ],
)
def test_errors_are_classified_without_exposing_provider_body(config, response, reason):
    with pytest.raises(MapServiceError) as exc_info:
        client(config, lambda request: response).search_pois("西湖")

    assert exc_info.value.reason is reason
    assert "secret" not in str(exc_info.value)


def test_network_timeout_retries_and_raises_safe_error(config, monkeypatch):
    calls = []
    monkeypatch.setattr("backend.app.integrations._amap_http.time.sleep", calls.append)

    def handler(request):
        raise httpx.ReadTimeout("secret request URL", request=request)

    with pytest.raises(MapServiceError) as exc_info:
        client(config, handler).search_pois("西湖")

    assert exc_info.value.reason is FailureReason.TIMEOUT
    assert "secret" not in str(exc_info.value)
    assert calls == [1]
