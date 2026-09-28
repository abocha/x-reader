from fastapi.testclient import TestClient

from x_reader.app import app, create_app
from x_reader.reader import TwscrapeReader


POST_FIELDS = {
    "id", "url", "created_at", "text", "author", "is_reply", "is_repost",
    "is_quote", "is_pinned", "conversation_id", "reply_to_id", "metrics",
    "links", "media", "lang", "mentions", "hashtags", "possibly_sensitive",
    "card", "quoted_post", "reposted_post",
}


def post(post_id=123, *, author_id=1, username="alice", reply_to=None, conversation=123):
    return {
        "id": post_id, "url": f"https://x.com/{username}/status/{post_id}",
        "date": "2026-09-03T19:00:00Z", "rawContent": "Astra is here.",
        "user": {"id": author_id, "username": username, "displayname": "Alice"},
        "replyCount": 1, "retweetCount": 2, "likeCount": 3,
        "quoteCount": 4, "bookmarkedCount": 5, "viewCount": 6,
        "conversationId": conversation, "inReplyToTweetId": reply_to,
        "links": [], "media": {"photos": [], "videos": [], "animated": []},
    }


class FakeReader:
    def __init__(self):
        self.profile = {"id": 1, "username": "alice", "pinnedIds": []}
        self.timeline = [post()]
        self.search_items = [post()]
        self.posts = {123: post()}
        self.thread_items = [post()]
        self.calls = []

    async def user(self, username):
        self.calls.append(("user", username))
        return self.profile if username == "alice" else None

    async def user_posts(self, username, limit):
        self.calls.append(("user_posts", username, limit))
        return self.timeline

    async def search(self, query, limit):
        self.calls.append(("search", query, limit))
        return self.search_items

    async def tweet(self, tweet_id):
        self.calls.append(("tweet", tweet_id))
        return self.posts.get(tweet_id)

    async def conversation(self, tweet_id, limit):
        self.calls.append(("conversation", tweet_id, limit))
        return self.thread_items


def test_health_endpoint():
    assert TestClient(create_app(FakeReader())).get("/health").json() == {"status": "ok"}


def test_default_app_has_twscrape_reader_and_service():
    assert isinstance(app.state.reader, TwscrapeReader)
    assert app.state.service.reader is app.state.reader


def test_post_endpoint_complete_public_shape():
    response = TestClient(create_app(FakeReader())).get("/v1/tweets/123")
    assert response.status_code == 200
    assert response.json() == {
        "id": "123", "url": "https://x.com/alice/status/123",
        "created_at": "2026-09-03T19:00:00Z", "text": "Astra is here.",
        "author": {"id": "1", "username": "alice", "name": "Alice"},
        "is_reply": False, "is_repost": False, "is_quote": False, "is_pinned": False,
        "conversation_id": "123", "reply_to_id": None,
        "metrics": {"replies": 1, "reposts": 2, "likes": 3, "quotes": 4, "bookmarks": 5, "views": 6},
        "links": [], "media": {"photos": [], "videos": [], "animated": []},
        "lang": None, "mentions": [], "hashtags": [], "possibly_sensitive": None,
        "card": None, "quoted_post": None, "reposted_post": None,
    }


def test_search_route_preserves_array_contract_and_filters_authors():
    reader = FakeReader()
    reader.search_items.append(post(124, author_id=2, username="bob"))
    response = TestClient(create_app(reader)).get("/v1/search", params={"q": "Astra", "from": "@alice", "limit": 2})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["123"]
    assert set(response.json()[0]) == POST_FIELDS
    assert response.json()[0]["author"] == {"id": "1", "username": "alice", "name": "Alice"}
    assert ("search", "(from:alice) (Astra)", 40) in reader.calls


def test_search_route_allows_query_without_authors_and_limits_results():
    reader = FakeReader()
    reader.search_items = [post(123), post(124)]
    response = TestClient(create_app(reader)).get("/v1/search", params={"q": "Astra", "limit": 1})
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["123"]
    assert ("search", "Astra", 40) in reader.calls


def test_user_posts_route_keeps_array_contract_and_excludes_foreign_author():
    reader = FakeReader()
    reader.timeline.append(post(124, author_id=2, username="bob"))
    response = TestClient(create_app(reader)).get("/v1/users/alice/posts")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["123"]
    assert set(response.json()[0]) == POST_FIELDS | {"timeline_item_type"}
    assert response.json()[0]["timeline_item_type"] == "post"


def test_user_posts_route_enforces_requested_limit():
    reader = FakeReader()
    reader.timeline = [post(123), post(124)]
    response = TestClient(create_app(reader)).get("/v1/users/alice/posts", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert ("user_posts", "alice", 40) in reader.calls


def test_thread_route_keeps_array_contract():
    reader = FakeReader()
    reader.thread_items = [post(125, conversation=123, author_id=2, username="bob", reply_to=123), post(124, conversation=123, reply_to=123), post()]
    response = TestClient(create_app(reader)).get("/v1/tweets/123/thread")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["124", "123"]
    assert all(set(item) == POST_FIELDS for item in response.json())
    assert ("conversation", 123, 60) in reader.calls


def test_thread_route_enforces_requested_limit():
    reader = FakeReader()
    reader.thread_items = [post(123), post(124, conversation=123, reply_to=123)]
    response = TestClient(create_app(reader)).get("/v1/tweets/123/thread", params={"limit": 1})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_route_validation_and_not_found_errors():
    client = TestClient(create_app(FakeReader()))
    assert client.get("/v1/tweets/0").status_code == 422
    assert client.get("/v1/tweets/999").json() == {"detail": "Tweet not found"}
    assert client.get("/v1/users/missing/posts").json() == {"detail": "User not found"}
    assert client.get("/v1/users/bad%29name/posts").status_code == 422
    assert client.get("/v1/search", params={"q": "topic", "from": "bad)name"}).status_code == 422
    assert client.get("/v1/search", params={"q": "topic", "from": " , , "}).json() == {"detail": "At least one author is required"}
    assert client.get("/v1/search", params={"q": "x" * 201}).status_code == 422
    assert client.get("/v1/search").status_code == 422
    assert client.get("/v1/tweets/123/thread", params={"limit": 0}).status_code == 422
    assert client.get("/v1/users/alice/posts", params={"limit": 51}).status_code == 422


def test_rate_limit_response_has_retry_after_and_per_client_budget():
    client = TestClient(create_app(FakeReader(), rate_limit=1, rate_window_seconds=3600))
    first = client.get("/v1/tweets/123", headers={"X-Forwarded-For": "203.0.113.1"})
    second = client.get("/v1/tweets/123", headers={"X-Forwarded-For": "203.0.113.1"})
    other = client.get("/v1/tweets/123", headers={"X-Forwarded-For": "203.0.113.2"})
    assert (first.status_code, second.status_code, other.status_code) == (200, 429, 200)
    assert second.json() == {"detail": "Rate limit exceeded"}
    assert second.headers["retry-after"] == "3600"
