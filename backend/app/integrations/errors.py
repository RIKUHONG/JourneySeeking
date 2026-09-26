"""Errors shared by external service adapters and their callers."""

from enum import Enum
from typing import ClassVar


class FailureReason(str, Enum):
    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PROVIDER = "provider"
    INVALID_RESPONSE = "invalid_response"


_MESSAGES = {
    FailureReason.CONFIGURATION: "服务配置缺失或无效",
    FailureReason.TIMEOUT: "服务请求超时",
    FailureReason.NETWORK: "服务网络请求失败",
    FailureReason.PROVIDER: "服务提供方返回错误",
    FailureReason.INVALID_RESPONSE: "服务返回的数据无效",
}


class ExternalServiceError(RuntimeError):
    service: ClassVar[str]
    code: ClassVar[str]

    def __init__(self, reason: FailureReason) -> None:
        self.reason = reason
        super().__init__(f"{self.service}{_MESSAGES[reason]}")


class MapServiceError(ExternalServiceError):
    service = "地图"
    code = "MAP_SERVICE_ERROR"


class WeatherServiceError(ExternalServiceError):
    service = "天气"
    code = "WEATHER_SERVICE_ERROR"
