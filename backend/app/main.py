"""FastAPI entry point for the 觅旅（MiliTravel）backend."""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .integrations.moma_client import (
    MomaAuthenticationError,
    MomaClient,
    MomaError,
    MomaRateLimitError,
)

app = FastAPI(
    title="觅旅 MiliTravel API",
    version="0.1.0",
    description="觅旅旅行规划平台后端 API",
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)


class ChatResponse(BaseModel):
    content: str
    model: str | None = None
    request_id: str | None = None
    usage: dict = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        result = MomaClient().chat(
            [message.model_dump() for message in request.messages],
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )
    except MomaAuthenticationError as exc:
        raise HTTPException(status_code=502, detail="MoMA 认证或权限失败。") from exc
    except MomaRateLimitError as exc:
        raise HTTPException(status_code=429, detail="MoMA 当前请求受限，请稍后重试。") from exc
    except MomaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        content=result.content,
        model=result.model,
        request_id=result.request_id,
        usage=dict(result.usage),
    )
