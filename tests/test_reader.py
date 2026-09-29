import asyncio
import importlib

import pytest


def test_twscrape_reader_search_returns_plain_dicts():
    reader_module = importlib.import_module("x_reader.reader")
    TwscrapeReader = getattr(reader_module, "TwscrapeReader", None)

    assert TwscrapeReader is not None

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


def test_twscrape_reader_user_posts_resolves_username_to_id():
    reader_module = importlib.import_module("x_reader.reader")
    TwscrapeReader = reader_module.TwscrapeReader

    class FakeUser:
        id = 42

    class FakeTweet:
        def __init__(self, tweet_id: int):
            self.tweet_id = tweet_id

        def dict(self) -> dict:
            return {
                "id": self.tweet_id,
                "user": {"username": "OpenAI"},
            }

    class FakeApi:
        async def user_by_login(self, username: str):
            assert username == "OpenAI"
            return FakeUser()

        async def user_tweets(self, uid: int, limit: int):
            assert uid == 42
            assert limit == 2

            for tweet_id in [10, 11]:
                yield FakeTweet(tweet_id)

    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(
        reader.user_posts(
            username="OpenAI",
            limit=2,
        )
    )

    assert result == [
        {"id": 10, "user": {"username": "OpenAI"}},
        {"id": 11, "user": {"username": "OpenAI"}},
    ]


def test_twscrape_reader_tweet_returns_plain_dict():
    reader_module = importlib.import_module("x_reader.reader")
    TwscrapeReader = reader_module.TwscrapeReader

    class FakeTweet:
        def dict(self) -> dict:
            return {
                "id": 123,
                "user": {"username": "OpenAI"},
            }

    class FakeApi:
        async def tweet_details(self, tweet_id: int):
            assert tweet_id == 123
            return FakeTweet()

    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(reader.tweet(tweet_id=123))

    assert result == {
        "id": 123,
        "user": {"username": "OpenAI"},
    }


def test_twscrape_reader_thread_returns_plain_dicts():
    reader_module = importlib.import_module("x_reader.reader")
    TwscrapeReader = reader_module.TwscrapeReader

    class FakeTweet:
        def __init__(self, tweet_id: int):
            self.tweet_id = tweet_id

        def dict(self) -> dict:
            return {
                "id": self.tweet_id,
                "user": {"username": "OpenAI"},
            }

    class FakeApi:
        async def tweet_thread(self, tweet_id: int, limit: int):
            assert tweet_id == 123
            assert limit == 20

            for item_id in [123, 124, 999]:
                yield FakeTweet(item_id)

    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(
        reader.thread(
            tweet_id=123,
            limit=20,
        )
    )

    assert result == [
        {"id": 123, "user": {"username": "OpenAI"}},
        {"id": 124, "user": {"username": "OpenAI"}},
        {"id": 999, "user": {"username": "OpenAI"}},
    ]


def test_twscrape_reader_user_posts_returns_none_when_user_missing():
    reader_module = importlib.import_module("x_reader.reader")
    TwscrapeReader = reader_module.TwscrapeReader

    class FakeApi:
        async def user_by_login(self, username: str):
            assert username == "does_not_exist"

        async def user_tweets(self, uid: int, limit: int):
            raise AssertionError("user_tweets must not be called")
            yield

    reader = TwscrapeReader(api=FakeApi())

    result = asyncio.run(
        reader.user_posts(
            username="does_not_exist",
            limit=20,
        )
    )

    assert result is None


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
    reader_module = importlib.import_module("x_reader.reader")
    calls = []

    class FakeItem:
        def dict(self) -> dict:
            return payload.copy()

    class FakeApi:
        async def fetch(self, value):
            calls.append(value)
            return None if missing else FakeItem()

    setattr(FakeApi, api_method, FakeApi.fetch)
    reader = reader_module.TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(argument))

    assert calls == [argument]
    assert result == (None if missing else payload)
    if not missing:
        assert type(result) is dict


@pytest.mark.parametrize(
    ("method", "api_method"),
    [
        ("user_posts", "user_tweets"),
        ("user_posts_and_replies", "user_tweets_and_replies"),
    ],
)
@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_twscrape_reader_user_timelines(method, api_method, missing, empty):
    reader_module = importlib.import_module("x_reader.reader")
    calls = []
    payloads = [] if empty else [
        {"id": 10, "inReplyToTweetId": None},
        {"id": 11, "inReplyToTweetId": 9},
    ]

    class FakeUser:
        id = 42

    class FakeTweet:
        def __init__(self, payload: dict):
            self.payload = payload

        def dict(self) -> dict:
            return self.payload.copy()

    class FakeApi:
        async def user_by_login(self, username: str):
            calls.append(("user_by_login", username))
            return None if missing else FakeUser()

        async def timeline(self, uid: int, *, limit: int):
            calls.append((api_method, uid, limit))
            for payload in payloads:
                yield FakeTweet(payload)

    setattr(FakeApi, api_method, FakeApi.timeline)
    reader = reader_module.TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(username="OpenAI", limit=2))

    assert result == (None if missing else payloads)
    assert calls == (
        [("user_by_login", "OpenAI")]
        if missing
        else [("user_by_login", "OpenAI"), (api_method, 42, 2)]
    )


@pytest.mark.parametrize(
    ("method", "api_method"),
    [
        ("user_posts_by_id", "user_tweets"),
        ("user_posts_and_replies_by_id", "user_tweets_and_replies"),
    ],
)
def test_twscrape_reader_id_timelines_skip_profile_lookup(method, api_method):
    reader_module = importlib.import_module("x_reader.reader")
    calls = []

    class FakeTweet:
        def dict(self):
            return {"id": 10}

    class FakeApi:
        async def user_by_login(self, username):
            raise AssertionError("ID timeline must not resolve username")

        async def timeline(self, user_id, *, limit):
            calls.append((api_method, user_id, limit))
            yield FakeTweet()

    setattr(FakeApi, api_method, FakeApi.timeline)
    reader = reader_module.TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(user_id=42, limit=2))

    assert result == [{"id": 10}]
    assert calls == [(api_method, 42, 2)]


@pytest.mark.parametrize(
    ("method", "api_method"),
    [
        ("tweet_replies", "tweet_replies"),
        ("conversation", "tweet_thread"),
        ("thread", "tweet_thread"),
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_twscrape_reader_tweet_timelines(method, api_method, empty):
    reader_module = importlib.import_module("x_reader.reader")
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
    reader = reader_module.TwscrapeReader(api=FakeApi())

    result = asyncio.run(getattr(reader, method)(tweet_id=123, limit=20))

    assert result == payloads
    assert calls == [(123, 20)]
    assert all(type(item) is dict for item in result)


def test_twscrape_reader_thread_delegates_to_conversation():
    reader_module = importlib.import_module("x_reader.reader")
    calls = []
    payloads = [{"id": 123}]

    class Reader(reader_module.TwscrapeReader):
        async def conversation(self, tweet_id: int, limit: int) -> list[dict]:
            calls.append((tweet_id, limit))
            return payloads

    reader = Reader(api=object())

    result = asyncio.run(reader.thread(tweet_id=123, limit=20))

    assert result is payloads
    assert calls == [(123, 20)]
