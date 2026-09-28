from typing import Any

from fastapi import FastAPI, HTTPException, Path as ApiPath, Query
from fastapi.responses import JSONResponse

from x_reader.errors import PostNotFound, UserNotFound
from x_reader.reader import TwscrapeReader
from x_reader.rate_limit import SlidingWindowRateLimiter
from x_reader.service import XReaderService


def create_app(
    reader: Any = None,
    rate_limit: int = 60,
    rate_window_seconds: float = 3600,
) -> FastAPI:
    app = FastAPI()

    if reader is None:
        reader = TwscrapeReader()

    app.state.reader = reader
    app.state.service = XReaderService(reader)
    app.state.rate_limiter = SlidingWindowRateLimiter(
        limit=rate_limit,
        window_seconds=rate_window_seconds,
    )

    @app.middleware("http")
    async def enforce_rate_limit(request, call_next):
        forwarded_for = request.headers.get("x-forwarded-for")

        if forwarded_for:
            client_key = forwarded_for.rsplit(",", 1)[-1].strip()
        elif request.client is not None:
            client_key = request.client.host
        else:
            client_key = "unknown"

        if (
            request.url.path.startswith("/v1/")
            and not app.state.rate_limiter.allow(client_key)
        ):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "Retry-After": str(int(rate_window_seconds)),
                },
            )

        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/search")
    async def search(
        q: str = Query(..., min_length=1, max_length=200),
        authors_raw: str | None = Query(default=None, alias="from"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict]:
        authors = [author.strip() for author in (authors_raw or "").split(",") if author.strip()]
        if authors_raw is not None and not authors:
            raise HTTPException(status_code=422, detail="At least one author is required")
        try:
            result = await app.state.service.search(query=q, authors=authors, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result["posts"]

    @app.get("/v1/users/{username}/posts")
    async def user_posts(
        username: str,
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict]:
        try:
            result = await app.state.service.read_user(username, limit=limit)
        except UserNotFound as exc:
            raise HTTPException(status_code=404, detail="User not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result["posts"]

    @app.get("/v1/tweets/{tweet_id}")
    async def tweet(
        tweet_id: int = ApiPath(..., gt=0),
    ) -> dict:
        try:
            result = await app.state.service.read_post(tweet_id)
        except PostNotFound as exc:
            raise HTTPException(status_code=404, detail="Tweet not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result["post"]

    @app.get("/v1/tweets/{tweet_id}/thread")
    async def tweet_thread(
        tweet_id: int = ApiPath(..., gt=0),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict]:
        try:
            result = await app.state.service.read_post(tweet_id, context="author_thread", limit=limit)
        except PostNotFound:
            return []
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result["context"]["posts"]

    return app


app = create_app()
