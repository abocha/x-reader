import asyncio

import pytest
from twscrape.accounts_pool import NoAccountError
from twscrape.http import NetworkError
from twscrape.queue_client import GqlFeaturesOutdatedError

from x_reader.errors import AccountUnavailable, UpstreamTimeout, UpstreamUnavailable
from x_reader.reader import TwscrapeReader


def test_twscrape_reader_search_returns_plain_dicts():
    class FakeTweet:
        def __init__(self, tweet_id: int):
            self.tweet_id = tweet_id

        def dict(self) -> dict:
            return {
                "id": self.tweet_id,
                "user": {"username": "OpenAI"},
            }

    class FakeApi:
        async def search(self, query: str, limit: int):
            assert query == "from:OpenAI Astra"
            assert limit == 2

            for tweet_id in [1, 2]:
                yield FakeTweet(tweet_id)

    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(
        reader.search(
            query="from:OpenAI Astra",
            limit=2,
        )
    )

    assert result == [
        {"id": 1, "user": {"username": "OpenAI"}},
        {"id": 2, "user": {"username": "OpenAI"}},
    ]


@pytest.mark.parametrize(
    ("method", "api_method", "argument", "payload"),
    [
        (
            "user",
            "user_by_login",
            "OpenAI",
            {
                "id": 42,
                "username": "OpenAI",
                "rawDescription": "",
                "friendsCount": 0,
                "blue": None,
                "pinnedIds": [],
            },
        ),
        (
            "user_about",
            "user_about",
            "OpenAI",
            {
                "screen_name": "OpenAI",
                "rest_id": 42,
                "account_based_in": None,
                "location_accurate": False,
                "username_changes": 0,
                "username_last_changed_at": None,
                "is_identity_verified": None,
                "verified_since_msec": None,
            },
        ),
        (
            "tweet",
            "tweet_details",
            123,
            {
                "id": 123,
                "inReplyToTweetId": None,
                "viewCount": None,
                "hashtags": ["example"],
                "mentionedUsers": [],
                "possibly_sensitive": False,
            },
        ),
    ],
)
@pytest.mark.parametrize("missing", [False, True])
def test_twscrape_reader_single_items(method, api_method, argument, payload, missing):
    calls = []

    class FakeItem:
        def dict(self) -> dict:
            return payload.copy()

    class FakeApi:
        async def fetch(self, value):
            calls.append(value)
            return None if missing else FakeItem()

    setattr(FakeApi, api_method, FakeApi.fetch)
    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(argument))

    assert calls == [argument]
    assert result == (None if missing else payload)
    if not missing:
        assert type(result) is dict


@pytest.mark.parametrize(
    ("method", "api_method"),
    [
        ("user_posts_by_id", "user_tweets"),
        ("user_posts_and_replies_by_id", "user_tweets_and_replies"),
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_twscrape_reader_id_timelines_skip_profile_lookup(method, api_method, empty):
    calls = []

    class FakeTweet:
        def dict(self):
            return {"id": 10}

    class FakeApi:
        async def user_by_login(self, username):
            raise AssertionError("ID timeline must not resolve username")

        async def timeline(self, user_id, *, limit):
            calls.append((api_method, user_id, limit))
            if not empty:
                yield FakeTweet()

    setattr(FakeApi, api_method, FakeApi.timeline)
    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(user_id=42, limit=2))

    assert result == ([] if empty else [{"id": 10}])
    assert calls == [(api_method, 42, 2)]


@pytest.mark.parametrize(
    ("method", "api_method"),
    [
        ("tweet_replies", "tweet_replies"),
        ("conversation", "tweet_thread"),
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_twscrape_reader_tweet_timelines(method, api_method, empty):
    calls = []
    payloads = [] if empty else [
        {
            "id": 125,
            "conversationId": 123,
            "inReplyToTweetId": 123,
            "user": {"username": "other"},
            "viewCount": None,
        },
        {
            "id": 124,
            "conversationId": 123,
            "inReplyToTweetId": 123,
            "user": {"username": "OpenAI"},
            "viewCount": 0,
        },
    ]

    class FakeTweet:
        def __init__(self, payload: dict):
            self.payload = payload

        def dict(self) -> dict:
            return self.payload.copy()

    class FakeApi:
        async def timeline(self, tweet_id: int, *, limit: int):
            calls.append((tweet_id, limit))
            for payload in payloads:
                yield FakeTweet(payload)

    setattr(FakeApi, api_method, FakeApi.timeline)
    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(tweet_id=123, limit=20))

    assert result == payloads
    assert calls == [(123, 20)]
    assert all(type(item) is dict for item in result)


def test_empty_account_pool_reports_unavailability_instead_of_empty_search(tmp_path):
    reader = TwscrapeReader(db_path=tmp_path / "accounts.db")
    with pytest.raises(AccountUnavailable, match="No X account is available"):
        asyncio.run(reader.search("topic", 1))


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("error,expected", [
    (NoAccountError("private account"), AccountUnavailable),
    (NetworkError("private proxy"), UpstreamUnavailable),
    (GqlFeaturesOutdatedError("private response"), UpstreamUnavailable),
])
def test_upstream_errors_are_classified_without_exposing_details(streamed, error, expected):
    class FakeApi:
        async def tweet_details(self, tweet_id):
            raise error

        async def search(self, query, limit):
            raise error
            yield

    reader = TwscrapeReader(api=FakeApi())
    with pytest.raises(expected) as caught:
        asyncio.run(reader.search("topic", 1) if streamed else reader.tweet(1))
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("streamed", [False, True])
def test_upstream_timeout_aborts_waiting_and_closes_stream(streamed):
    closed = []

    class FakeApi:
        async def tweet_details(self, tweet_id):
            await asyncio.Event().wait()

        async def search(self, query, limit):
            try:
                await asyncio.Event().wait()
                yield
            finally:
                closed.append(True)

    reader = TwscrapeReader(api=FakeApi(), request_timeout_seconds=0.01)
    with pytest.raises(UpstreamTimeout, match="timed out"):
        asyncio.run(reader.search("topic", 1) if streamed else reader.tweet(1))
    assert closed == ([True] if streamed else [])


def test_cancelling_a_stream_releases_it_and_preserves_cancellation():
    async def run():
        started = asyncio.Event()
        closed = asyncio.Event()

        class FakeApi:
            async def search(self, query, limit):
                try:
                    started.set()
                    await asyncio.Event().wait()
                    yield
                finally:
                    closed.set()

        reader = TwscrapeReader(api=FakeApi())
        task = asyncio.create_task(reader.search("topic", 1))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()

    asyncio.run(run())
