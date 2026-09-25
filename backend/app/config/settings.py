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
    moma_api_url: str = os.getenv("MOMA_API_URL", "https://zhenze-huhehaote.cmecloud.cn/v1/chat/completions")
    moma_model: str = os.getenv("MOMA_MODEL", "deepseek-v4-flash-0731")
    moma_api_key: str = os.getenv("MOMA_API_KEY", "").strip()
    moma_timeout_seconds: float = float(os.getenv("MOMA_TIMEOUT_SECONDS", "60"))
    moma_max_retries: int = int(os.getenv("MOMA_MAX_RETRIES", "2"))

    def validate_moma(self) -> None:
        if not self.moma_api_key.strip():
            raise ValueError("MOMA_API_KEY 未设置，请在 backend/.env 或环境变量中配置。")
        if not self.moma_api_url.startswith(("http://", "https://")):
            raise ValueError("MOMA_API_URL 必须是完整的 http(s) URL。")


settings = Settings()
