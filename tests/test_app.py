import importlib

from fastapi.testclient import TestClient


def test_health_endpoint():
    app_module = importlib.import_module("x_reader.app")
    app = getattr(app_module, "app", None)

    assert app is not None

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_endpoint_uses_reader_and_returns_normalized_results():
    app_module = importlib.import_module("x_reader.app")
    create_app = getattr(app_module, "create_app", None)

    assert create_app is not None

    def tweet(tweet_id: int, username: str, name: str) -> dict:
        return {
            "id": tweet_id,
            "url": f"https://x.com/{username}/status/{tweet_id}",
            "date": "2026-09-03T19:00:00Z",
            "rawContent": f"Tweet {tweet_id}",
            "user": {
                "username": username,
                "displayname": name,
            },
            "replyCount": 1,
            "retweetCount": 2,
            "likeCount": 3,
            "quoteCount": 4,
            "bookmarkedCount": 5,
            "viewCount": 6,
            "conversationId": tweet_id,
            "inReplyToTweetId": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        }

    class FakeReader:
        async def search(self, query: str, limit: int) -> list[dict]:
            assert query == "(from:OpenAI OR from:sama) (Astra)"
            assert limit == 20

            return [
                tweet(1, "OpenAI", "OpenAI"),
                tweet(2, "random_person", "Random Person"),
                tweet(3, "sama", "Sam Altman"),
            ]

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/search",
        params={
            "q": "Astra",
            "from": "OpenAI,sama",
            "limit": 2,
        },
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "1",
            "url": "https://x.com/OpenAI/status/1",
            "created_at": "2026-09-03T19:00:00Z",
            "text": "Tweet 1",
            "author": {
                "username": "OpenAI",
                "name": "OpenAI",
            },
            "metrics": {
                "replies": 1,
                "reposts": 2,
                "likes": 3,
                "quotes": 4,
                "bookmarks": 5,
                "views": 6,
            },
            "conversation_id": "1",
            "reply_to_id": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        },
        {
            "id": "3",
            "url": "https://x.com/sama/status/3",
            "created_at": "2026-09-03T19:00:00Z",
            "text": "Tweet 3",
            "author": {
                "username": "sama",
                "name": "Sam Altman",
            },
            "metrics": {
                "replies": 1,
                "reposts": 2,
                "likes": 3,
                "quotes": 4,
                "bookmarks": 5,
                "views": 6,
            },
            "conversation_id": "3",
            "reply_to_id": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        },
    ]


def test_default_app_has_reader():
    app_module = importlib.import_module("x_reader.app")

    assert hasattr(app_module.app.state, "reader")
    assert app_module.app.state.reader is not None


def test_user_posts_endpoint_returns_normalized_results():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    def tweet(tweet_id: int) -> dict:
        return {
            "id": tweet_id,
            "url": f"https://x.com/OpenAI/status/{tweet_id}",
            "date": "2026-09-03T19:00:00Z",
            "rawContent": f"Tweet {tweet_id}",
            "user": {
                "username": "OpenAI",
                "displayname": "OpenAI",
            },
            "replyCount": 1,
            "retweetCount": 2,
            "likeCount": 3,
            "quoteCount": 4,
            "bookmarkedCount": 5,
            "viewCount": 6,
            "conversationId": tweet_id,
            "inReplyToTweetId": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        }

    class FakeReader:
        async def user_posts(
            self,
            username: str,
            limit: int,
        ) -> list[dict]:
            assert username == "OpenAI"
            assert limit == 2

            return [
                tweet(10),
                tweet(11),
            ]

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/users/OpenAI/posts",
        params={"limit": 2},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["10", "11"]
    assert [item["author"]["username"] for item in response.json()] == [
        "OpenAI",
        "OpenAI",
    ]


def test_user_posts_endpoint_enforces_strict_limit():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    def tweet(tweet_id: int) -> dict:
        return {
            "id": tweet_id,
            "url": f"https://x.com/OpenAI/status/{tweet_id}",
            "date": "2026-09-03T19:00:00Z",
            "rawContent": f"Tweet {tweet_id}",
            "user": {
                "username": "OpenAI",
                "displayname": "OpenAI",
            },
            "replyCount": 0,
            "retweetCount": 0,
            "likeCount": 0,
            "quoteCount": 0,
            "bookmarkedCount": 0,
            "viewCount": 0,
            "conversationId": tweet_id,
            "inReplyToTweetId": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        }

    class FakeReader:
        async def user_posts(
            self,
            username: str,
            limit: int,
        ) -> list[dict]:
            assert username == "OpenAI"
            assert limit == 3

            return [
                tweet(1),
                tweet(2),
                tweet(3),
                tweet(4),
                tweet(5),
            ]

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/users/OpenAI/posts",
        params={"limit": 3},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["1", "2", "3"]


def test_thread_endpoint_keeps_author_chain_sorts_and_enforces_limit():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    def tweet(
        tweet_id: int,
        *,
        username: str,
        conversation_id: int,
        date: str,
    ) -> dict:
        return {
            "id": tweet_id,
            "url": f"https://x.com/{username}/status/{tweet_id}",
            "date": date,
            "rawContent": f"Tweet {tweet_id}",
            "user": {
                "username": username,
                "displayname": username,
            },
            "replyCount": 0,
            "retweetCount": 0,
            "likeCount": 0,
            "quoteCount": 0,
            "bookmarkedCount": 0,
            "viewCount": 0,
            "conversationId": conversation_id,
            "inReplyToTweetId": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        }

    class FakeReader:
        async def thread(
            self,
            tweet_id: int,
            limit: int,
        ) -> list[dict]:
            assert tweet_id == 100
            assert limit == 20

            return [
                tweet(
                    103,
                    username="OpenAI",
                    conversation_id=100,
                    date="2026-09-03T19:03:00Z",
                ),
                tweet(
                    100,
                    username="OpenAI",
                    conversation_id=100,
                    date="2026-09-03T19:00:00Z",
                ),
                tweet(
                    102,
                    username="random_reply",
                    conversation_id=100,
                    date="2026-09-03T19:02:00Z",
                ),
                tweet(
                    101,
                    username="OpenAI",
                    conversation_id=100,
                    date="2026-09-03T19:01:00Z",
                ),
                tweet(
                    999,
                    username="OpenAI",
                    conversation_id=999,
                    date="2026-09-03T18:00:00Z",
                ),
            ]

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/tweets/100/thread",
        params={"limit": 2},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["100", "101"]


def test_tweet_endpoint_returns_normalized_tweet():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    class FakeReader:
        async def tweet(self, tweet_id: int) -> dict:
            assert tweet_id == 123

            return {
                "id": 123,
                "url": "https://x.com/OpenAI/status/123",
                "date": "2026-09-03T19:00:00Z",
                "rawContent": "Astra is here.",
                "user": {
                    "username": "OpenAI",
                    "displayname": "OpenAI",
                },
                "replyCount": 1,
                "retweetCount": 2,
                "likeCount": 3,
                "quoteCount": 4,
                "bookmarkedCount": 5,
                "viewCount": 6,
                "conversationId": 123,
                "inReplyToTweetId": None,
                "links": [],
                "media": {
                    "photos": [],
                    "videos": [],
                    "animated": [],
                },
            }

    client = TestClient(create_app(FakeReader()))

    response = client.get("/v1/tweets/123")

    assert response.status_code == 200
    assert response.json()["id"] == "123"
    assert response.json()["text"] == "Astra is here."
    assert response.json()["author"]["username"] == "OpenAI"


def test_tweet_endpoint_returns_404_when_missing():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    class FakeReader:
        async def tweet(self, tweet_id: int):
            assert tweet_id == 999
            return None

    client = TestClient(create_app(FakeReader()))

    response = client.get("/v1/tweets/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Tweet not found"}


def test_search_endpoint_rejects_invalid_author_username():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    class FakeReader:
        async def search(self, query: str, limit: int):
            raise AssertionError("reader must not be called")

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/search",
        params={
            "q": "Astra",
            "from": "OpenAI) OR from:evil",
            "limit": 3,
        },
    )

    assert response.status_code == 422


def test_search_endpoint_rejects_empty_author_list():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    class FakeReader:
        async def search(self, query: str, limit: int):
            raise AssertionError("reader must not be called")

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/search",
        params={
            "q": "Astra",
            "from": " , , ",
            "limit": 3,
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "At least one author is required"
    }


def test_search_endpoint_rejects_overlong_query():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    class FakeReader:
        async def search(self, query: str, limit: int):
            raise AssertionError("reader must not be called")

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/search",
        params={
            "q": "x" * 201,
            "from": "OpenAI",
            "limit": 3,
        },
    )

    assert response.status_code == 422


def test_search_endpoint_allows_search_without_authors():
    app_module = importlib.import_module("x_reader.app")
    create_app = app_module.create_app

    def tweet(tweet_id: int, username: str) -> dict:
        return {
            "id": tweet_id,
            "url": f"https://x.com/{username}/status/{tweet_id}",
            "date": "2026-09-04T12:00:00Z",
            "rawContent": f"Tweet {tweet_id}",
            "user": {
                "username": username,
                "displayname": username,
            },
            "replyCount": 0,
            "retweetCount": 0,
            "likeCount": 0,
            "quoteCount": 0,
            "bookmarkedCount": 0,
            "viewCount": 0,
            "conversationId": tweet_id,
            "inReplyToTweetId": None,
            "links": [],
            "media": {
                "photos": [],
                "videos": [],
                "animated": [],
            },
        }

    class FakeReader:
        async def search(self, query: str, limit: int):
            assert query == "Astra OR GPT-6"
            assert limit == 20

            return [
                tweet(1, "OpenAI"),
                tweet(2, "sama"),
                tweet(3, "someone_else"),
            ]

    client = TestClient(create_app(FakeReader()))

    response = client.get(
        "/v1/search",
        params={
            "q": "Astra OR GPT-6",
            "limit": 2,
        },
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["1", "2"]
