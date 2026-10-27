import asyncio
import os
import sqlite3
from collections.abc import AsyncGenerator, Awaitable
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any, Literal

from twscrape import API
from twscrape.accounts_pool import NoAccountError
from twscrape.http import HttpError
from twscrape.queue_client import GqlFeaturesOutdatedError

from x_reader.errors import (
    AccountUnavailable,
    EndpointBusy,
    UpstreamTimeout,
    UpstreamUnavailable,
)


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

    async def _account_failure(self, queue: str) -> AccountUnavailable:
        unavailable = AccountUnavailable(
            "No X account is available. Check account status before retrying.", endpoint=queue,
        )
        pool = getattr(self.api, "pool", None)
        if pool is None:
            return unavailable
        try:
            async with asyncio.timeout(0.5):
                accounts = await pool.get_all()
        except (TimeoutError, sqlite3.Error, OSError):
            return unavailable
        active = [account for account in accounts if account.active]
        if not active:
            return unavailable
        now = datetime.now(UTC)
        locks = [account.locks.get(queue) for account in active]
        if all(lock is not None and lock > now for lock in locks):
            retry_after = max(1, ceil(min((lock - now).total_seconds() for lock in locks if lock is not None)))
            return EndpointBusy(
                "X accounts are temporarily locked for this endpoint. Retry after the indicated delay.",
                retry_after_seconds=retry_after, endpoint=queue,
            )
        # Availability can change between twscrape's acquisition and this read-only snapshot.
        return AccountUnavailable(str(unavailable), retryable=True, endpoint=queue)

    @asynccontextmanager
    async def _upstream_request(self, queue: str) -> AsyncGenerator[None, None]:
        try:
            async with asyncio.timeout(self.request_timeout_seconds):
                yield
        except NoAccountError as exc:
            raise await self._account_failure(queue) from exc
        except TimeoutError as exc:
            raise UpstreamTimeout("X request timed out. Retry later.", endpoint=queue) from exc
        except (HttpError, GqlFeaturesOutdatedError) as exc:
            raise UpstreamUnavailable(
                "X is temporarily unavailable or its API has changed. Retry later; "
                "if this persists, check the server.", endpoint=queue
            ) from exc

    async def _one(self, operation: Awaitable[Any], queue: str) -> dict | None:
        async with self._upstream_request(queue):
            result = await operation
            return None if result is None else result.dict()

    async def _many(self, items: AsyncGenerator[Any, None], queue: str) -> list[dict]:
        async with self._upstream_request(queue), aclosing(items):
            return [item.dict() async for item in items]

    async def search(
        self,
        query: str,
        limit: int,
        *,
        ranking: Literal["recent", "top"] = "recent",
    ) -> list[dict]:
        if ranking == "recent":
            items = self.api.search(query, limit=limit)
        else:
            items = self.api.search(query, limit=limit, kv={"product": "Top"})
        return await self._many(items, "SearchTimeline")

    async def user(
        self,
        username: str,
    ) -> dict | None:
        return await self._one(self.api.user_by_login(username), "UserByScreenName")

    async def user_about(
        self,
        username: str,
    ) -> dict | None:
        return await self._one(self.api.user_about(username), "AboutAccountQuery")

    async def user_posts_by_id(
        self,
        user_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.user_tweets(user_id, limit=limit), "UserTweets")

    async def user_posts_and_replies_by_id(
        self,
        user_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.user_tweets_and_replies(user_id, limit=limit), "UserTweetsAndReplies")

    async def tweet(
        self,
        tweet_id: int,
    ) -> dict | None:
        return await self._one(self.api.tweet_details(tweet_id), "TweetDetail")

    async def tweet_replies(
        self,
        tweet_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.tweet_replies(tweet_id, limit=limit), "TweetDetail")

    async def conversation(
        self,
        tweet_id: int,
        limit: int,
    ) -> list[dict]:
        return await self._many(self.api.tweet_thread(tweet_id, limit=limit), "TweetDetail")
