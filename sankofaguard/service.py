"""SankofaGuard service — a deployable normalizer proxy.

Two integration surfaces:
  • POST /normalize            → stateless normalization over HTTP (library API).
  • POST /v1/chat/completions  → OpenAI-compatible DROP-IN PROXY: normalizes user
    messages through SankofaGuard, then forwards to a backend (default OpenRouter)
    and returns the reply. Point an existing app at
    ``http://localhost:8000/v1/chat/completions`` to get guarded behavior with
    no code change.

Run:  python -m sankofaguard.service   (uvicorn on :8000)
Env:  SANKOFA_BACKEND_URL (default OpenRouter), SANKOFA_PORT (default 8000),
      OPENROUTER_API_KEY (passed through as the bearer by the caller).
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel

from sankofaguard.guard import SankofaGuard

GUARD = SankofaGuard()
BACKEND_URL = os.environ.get("SANKOFA_BACKEND_URL", "https://openrouter.ai/api/v1/chat/completions")

app = FastAPI(title="SankofaGuard", version="0.1.1")


class NormalizeReq(BaseModel):
    text: str
    lang: str = "yor"


class SpanOut(BaseModel):
    lang: str
    text: str


class NormalizeResp(BaseModel):
    canonical_text: str
    ops: list[str]
    spans: list[SpanOut]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "guard": "sankofaguard-v1"}


@app.post("/normalize", response_model=NormalizeResp)
def normalize(req: NormalizeReq) -> NormalizeResp:
    n = GUARD.normalize(req.text, req.lang)
    return NormalizeResp(
        canonical_text=n.canonical_text,
        ops=n.ops,
        spans=[SpanOut(lang=s.lang, text=s.text) for s in n.spans],
    )


@app.post("/v1/chat/completions")
async def chat_proxy(request: Request):
    """Drop-in proxy: normalize user turns, forward to backend, return the reply."""
    body = await request.json()
    auth = request.headers.get("Authorization")
    lang = body.pop("lang", "yor")
    for msg in body.get("messages", []):
        if msg.get("role") == "user":
            msg["content"] = GUARD.normalize(msg["content"], lang).canonical_text
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = auth
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(BACKEND_URL, json=body, headers=headers)
    return resp.json()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "sankofaguard.service:app",
        host="0.0.0.0",
        port=int(os.environ.get("SANKOFA_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
