from typing import Any

from twscrape import API


class TwscrapeReader:
    def __init__(
        self,
        db_path: str = "accounts.db",
        api: Any = None,
    ) -> None:
        self.api = api or API(db_path)

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
    ) -> list[dict]:
        user = await self.api.user_by_login(username)

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
