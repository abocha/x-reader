import asyncio
import os
from collections.abc import AsyncGenerator, Awaitable
from contextlib import aclosing, asynccontextmanager
from pathlib import Path
from typing import Any

from twscrape import API
from twscrape.accounts_pool import NoAccountError
from twscrape.http import HttpError
from twscrape.queue_client import GqlFeaturesOutdatedError

from x_reader.errors import AccountUnavailable, UpstreamTimeout, UpstreamUnavailable


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
        *,
        request_timeout_seconds: float = 20,
    ) -> None:
        self.request_timeout_seconds = request_timeout_seconds
        if api is not None:
            self.api = api
            return

        resolved_db_path = (
            Path(db_path).expanduser().resolve()
            if db_path is not None
            else default_db_path()
        )
        self.api = API(
            str(resolved_db_path), raise_when_no_account=True,
            wait_timeout=5, wait_interval=0.5,
        )

    @asynccontextmanager
    async def _upstream_request(self) -> AsyncGenerator[None, None]:
        try:
            async with asyncio.timeout(self.request_timeout_seconds):
                yield
        except NoAccountError as exc:
            raise AccountUnavailable(
                "No X account is available. Check account status or retry later."
            ) from exc
        except TimeoutError as exc:
            raise UpstreamTimeout("X request timed out. Retry later.") from exc
        except (HttpError, GqlFeaturesOutdatedError) as exc:
            raise UpstreamUnavailable(
                "X is temporarily unavailable or its API has changed. Retry later; "
                "if this persists, check the server."
            ) from exc

    async def _one(self, operation: Awaitable[Any]) -> dict | None:
        async with self._upstream_request():
            result = await operation
            return None if result is None else result.dict()

    async def _many(self, items: AsyncGenerator[Any, None]) -> list[dict]:
        async with self._upstream_request(), aclosing(items):
            return [item.dict() async for item in items]

    async def search(
        self,
        query: str,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.search(query, limit=limit))

    async def user(
        self,
        username: str,
    ) -> dict | None:
        return await self._one(self.api.user_by_login(username))

    async def user_about(
        self,
        username: str,
    ) -> dict | None:
        return await self._one(self.api.user_about(username))

    async def user_posts_by_id(
        self,
        user_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.user_tweets(user_id, limit=limit))

    async def user_posts_and_replies_by_id(
        self,
        user_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.user_tweets_and_replies(user_id, limit=limit))

    async def tweet(
        self,
        tweet_id: int,
    ) -> dict | None:
        return await self._one(self.api.tweet_details(tweet_id))

    async def tweet_replies(
        self,
        tweet_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.tweet_replies(tweet_id, limit=limit))

    async def conversation(
        self,
        tweet_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.tweet_thread(tweet_id, limit=limit))
