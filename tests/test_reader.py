import asyncio
import importlib


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
