"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    # Resolve the project-local file explicitly so startup works from either
    # the repository root or the backend directory.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@dataclass(frozen=True)
class Settings:
    moma_api_url: str = os.getenv(
        "MOMA_API_URL", "https://zhenze-huhehaote.cmecloud.cn/v1/chat/completions"
    )
    moma_model: str = os.getenv("MOMA_MODEL", "deepseek-v4-flash-0731")
    moma_api_key: str = os.getenv("MOMA_API_KEY", "").strip()
    moma_timeout_seconds: float = float(os.getenv("MOMA_TIMEOUT_SECONDS", "60"))
    moma_max_retries: int = int(os.getenv("MOMA_MAX_RETRIES", "2"))
    amap_api_key: str = os.getenv("AMAP_API_KEY", "").strip()
    amap_base_url: str = os.getenv("AMAP_BASE_URL", "https://restapi.amap.com/v3")
    amap_timeout_seconds: float = float(os.getenv("AMAP_TIMEOUT_SECONDS", "10"))
    amap_max_retries: int = int(os.getenv("AMAP_MAX_RETRIES", "2"))
    weather_api_key: str = os.getenv("WEATHER_API_KEY", "").strip()
    weather_base_url: str = os.getenv("WEATHER_BASE_URL", "https://restapi.amap.com/v3")
    weather_timeout_seconds: float = float(os.getenv("WEATHER_TIMEOUT_SECONDS", "10"))
    weather_max_retries: int = int(os.getenv("WEATHER_MAX_RETRIES", "2"))

    def validate_moma(self) -> None:
        if not self.moma_api_key.strip():
            raise ValueError("MOMA_API_KEY 未设置，请在 backend/.env 或环境变量中配置。")
        if not self.moma_api_url.startswith(("http://", "https://")):
            raise ValueError("MOMA_API_URL 必须是完整的 http(s) URL。")

    def validate_map(self) -> None:
        self._validate_external(
            "AMAP",
            self.amap_api_key,
            self.amap_base_url,
            self.amap_timeout_seconds,
            self.amap_max_retries,
        )

    def validate_weather(self) -> None:
        self._validate_external(
            "WEATHER",
            self.weather_api_key,
            self.weather_base_url,
            self.weather_timeout_seconds,
            self.weather_max_retries,
        )

    @staticmethod
    def _validate_external(
        prefix: str, api_key: str, base_url: str, timeout_seconds: float, max_retries: int
    ) -> None:
        if not api_key:
            raise ValueError(f"{prefix}_API_KEY 未设置。")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"{prefix}_BASE_URL 必须是完整的 http(s) URL。")
        if not 0 < timeout_seconds < float("inf"):
            raise ValueError(f"{prefix}_TIMEOUT_SECONDS 必须是正的有限数值。")
        if max_retries < 0:
            raise ValueError(f"{prefix}_MAX_RETRIES 不能为负数。")


settings = Settings()
