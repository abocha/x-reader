import os
from pathlib import Path
from typing import Any

from twscrape import API


def default_db_path() -> Path:
    configured = os.environ.get("X_READER_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()

    return (Path(__file__).resolve().parents[2] / "accounts.db").resolve()


class TwscrapeReader:
    def __init__(
        self,
        db_path: str | Path | None = None,
        api: Any = None,
    ) -> None:
        if api is not None:
            self.api = api
            return

        resolved_db_path = (
            Path(db_path).expanduser().resolve()
            if db_path is not None
            else default_db_path()
        )
        self.api = API(str(resolved_db_path))

    async def search(
        self,
        query: str,
        limit: int,
    ) -> list[dict]:
        results = []

        async for tweet in self.api.search(query, limit=limit):
            results.append(tweet.dict())

        return results

    async def user_posts(
        self,
        username: str,
        limit: int,
    ) -> list[dict] | None:
        user = await self.api.user_by_login(username)

        if user is None:
            return None

        results = []

        async for tweet in self.api.user_tweets(user.id, limit=limit):
            results.append(tweet.dict())

        return results

    async def tweet(
        self,
        tweet_id: int,
    ) -> dict | None:
        result = await self.api.tweet_details(tweet_id)

        if result is None:
            return None

        return result.dict()

    async def thread(
        self,
        tweet_id: int,
        limit: int,
    ) -> list[dict]:
        results = []

        async for tweet in self.api.tweet_thread(tweet_id, limit=limit):
            results.append(tweet.dict())

        return results
