from typing import Any

from fastapi import FastAPI, HTTPException, Query

from x_reader.normalize import normalize_tweet
from x_reader.reader import TwscrapeReader
from x_reader.search import build_search_query, filter_search_results, validate_authors
from x_reader.thread import filter_author_thread


def create_app(reader: Any = None) -> FastAPI:
    app = FastAPI()

    if reader is None:
        reader = TwscrapeReader()

    app.state.reader = reader

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/search")
    async def search(
        q: str = Query(..., min_length=1, max_length=200),
        authors_raw: str | None = Query(default=None, alias="from"),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict]:
        if authors_raw is None:
            authors = []
        else:
            authors = [
                author.strip()
                for author in authors_raw.split(",")
                if author.strip()
            ]

            try:
                validate_authors(authors)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc),
                ) from exc

        query = build_search_query(q, authors)
        fetch_limit = max(20, limit)

        results = await app.state.reader.search(query, fetch_limit)

        filtered = filter_search_results(
            results,
            authors=authors,
            limit=limit,
        )

        return [normalize_tweet(tweet) for tweet in filtered]

    @app.get("/v1/users/{username}/posts")
    async def user_posts(
        username: str,
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict]:
        results = await app.state.reader.user_posts(
            username=username,
            limit=limit,
        )

        return [
            normalize_tweet(tweet)
            for tweet in results[:limit]
        ]

    @app.get("/v1/tweets/{tweet_id}")
    async def tweet(
        tweet_id: int,
    ) -> dict:
        result = await app.state.reader.tweet(tweet_id=tweet_id)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Tweet not found",
            )

        return normalize_tweet(result)

    @app.get("/v1/tweets/{tweet_id}/thread")
    async def tweet_thread(
        tweet_id: int,
        limit: int = Query(default=20, ge=1, le=50),
    ) -> list[dict]:
        fetch_limit = max(20, limit)

        results = await app.state.reader.thread(
            tweet_id=tweet_id,
            limit=fetch_limit,
        )

        filtered = filter_author_thread(results)

        return [
            normalize_tweet(tweet)
            for tweet in filtered[:limit]
        ]

    return app


app = create_app()
