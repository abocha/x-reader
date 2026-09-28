import pytest
from mcp import Client

from x_reader.mcp_server import create_mcp_server


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def post(post_id=123, author_id=1, *, reply_to=None):
    return {
        "id": post_id, "date": "2026-09-03T19:00:00Z", "rawContent": f"post {post_id}",
        "user": {"id": author_id, "username": "alice" if author_id == 1 else "bob"},
        "conversationId": 123, "inReplyToTweetId": reply_to,
    }


class FakeReader:
    def __init__(self):
        self.profile = {"id": 1, "username": "alice", "pinnedIds": []}
        self.search_items = [post()]
        self.timeline = [post()]
        self.posts = {123: post()}
        self.conversation_items = [post(), post(124, reply_to=123), post(125, 2, reply_to=123)]
        self.calls = []

    async def user(self, username):
        self.calls.append(("user", username))
        return self.profile if username == "alice" else None

    async def user_posts_by_id(self, user_id, limit):
        self.calls.append(("user_posts_by_id", user_id, limit))
        return self.timeline

    async def user_posts_and_replies_by_id(self, user_id, limit):
        self.calls.append(("user_posts_and_replies_by_id", user_id, limit))
        return self.timeline

    async def user_about(self, username):
        return {"account_based_in": "US"}

    async def search(self, query, limit):
        self.calls.append(("search", query, limit))
        return self.search_items

    async def tweet(self, tweet_id):
        self.calls.append(("tweet", tweet_id))
        return self.posts.get(tweet_id)

    async def conversation(self, tweet_id, limit):
        self.calls.append(("conversation", tweet_id, limit))
        return self.conversation_items

    async def tweet_replies(self, tweet_id, limit):
        return [post(125, 2, reply_to=123)]


async def test_lists_compatibility_and_rich_read_only_tools():
    async with Client(create_mcp_server(FakeReader())) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == {"search_x", "get_x_user_posts", "get_x_post", "get_x_thread", "read_x_user", "read_x_post"}
    for tool in tools.values():
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
    assert "@handle" in tools["read_x_user"].description
    assert "post URL" in tools["read_x_post"].description
    assert "parent" in tools["read_x_post"].description
    assert "compact" in (tools["search_x"].description or "")
    assert "full" in (tools["read_x_user"].description or "")
    context_schema = tools["read_x_post"].input_schema["properties"]["context"]
    assert "parent" in context_schema["enum"]


async def test_compatibility_tools_delegate_and_preserve_response_shapes():
    reader = FakeReader()
    async with Client(create_mcp_server(reader)) as client:
        search = await client.call_tool("search_x", {"query": "topic", "authors": ["@alice"]})
        user = await client.call_tool("get_x_user_posts", {"username": "alice"})
        single = await client.call_tool("get_x_post", {"tweet_id": 123})
        thread = await client.call_tool("get_x_thread", {"tweet_id": 123})
    assert search.is_error is user.is_error is single.is_error is thread.is_error is False
    assert list(search.structured_content) == ["posts"]
    assert [item["id"] for item in search.structured_content["posts"]] == ["123"]
    assert [item["id"] for item in user.structured_content["posts"]] == ["123"]
    assert list(single.structured_content) == ["post"]
    assert single.structured_content["post"]["id"] == "123"
    assert [item["id"] for item in thread.structured_content["posts"]] == ["123", "124"]
    assert ("conversation", 123, 60) in reader.calls
    for item in [search.structured_content["posts"][0], user.structured_content["posts"][0],
                 single.structured_content["post"], thread.structured_content["posts"][0]]:
        assert "metrics" in item


async def test_mcp_detail_defaults_and_explicit_projection():
    reader = FakeReader()
    reader.posts[124] = post(124, reply_to=123)
    async with Client(create_mcp_server(reader)) as client:
        search_full = await client.call_tool("search_x", {"query": "topic"})
        search_compact = await client.call_tool("search_x", {"query": "topic", "detail": "compact"})
        user_compact = await client.call_tool("read_x_user", {"user": "alice"})
        user_full = await client.call_tool("read_x_user", {"user": "alice", "detail": "full"})
        post_full = await client.call_tool("read_x_post", {"post": 124, "context": "parent"})
        post_compact = await client.call_tool("read_x_post", {"post": 124, "context": "parent", "detail": "compact"})
    assert all(not result.is_error for result in (
        search_full, search_compact, user_compact, user_full, post_full, post_compact
    ))
    assert "metrics" in search_full.structured_content["posts"][0]
    assert "metrics" not in search_compact.structured_content["posts"][0]
    assert "metrics" not in user_compact.structured_content["posts"][0]
    assert "metrics" in user_full.structured_content["posts"][0]
    assert "metrics" in post_full.structured_content["post"]
    assert "metrics" not in post_compact.structured_content["post"]
    assert "metrics" in post_full.structured_content["context"]["posts"][0]
    assert "metrics" not in post_compact.structured_content["context"]["posts"][0]
    assert reader.calls == [
        ("search", "topic", 60), ("search", "topic", 60),
        ("user", "alice"), ("user_posts_by_id", 1, 60),
        ("user", "alice"), ("user_posts_by_id", 1, 60),
        ("tweet", 124), ("tweet", 123), ("tweet", 124), ("tweet", 123),
    ]


async def test_rich_tools_support_locators_profile_and_context():
    reader = FakeReader()
    async with Client(create_mcp_server(reader)) as client:
        user = await client.call_tool("read_x_user", {"user": "https://x.com/alice", "include_about": True})
        single = await client.call_tool("read_x_post", {"post": "https://twitter.com/alice/status/123", "context": "conversation"})
    assert user.is_error is single.is_error is False
    assert user.structured_content["user"]["id"] == "1"
    assert user.structured_content["about"]["account_based_in"] == "US"
    assert single.structured_content["post"]["id"] == "123"
    assert single.structured_content["context"]["type"] == "conversation"
    assert [item["id"] for item in single.structured_content["context"]["posts"]] == ["124", "125"]
    assert single.structured_content["post"]["id"] not in [
        item["id"] for item in single.structured_content["context"]["posts"]
    ]


async def test_read_x_post_supports_parent_context():
    reader = FakeReader()
    reader.posts[124] = post(124, reply_to=123)

    async with Client(create_mcp_server(reader)) as client:
        result = await client.call_tool(
            "read_x_post", {"post": 124, "context": "parent"}
        )

    assert result.is_error is False
    assert result.structured_content["post"]["id"] == "124"
    assert result.structured_content["context"]["type"] == "parent"
    assert [item["id"] for item in result.structured_content["context"]["posts"]] == ["123"]
    assert reader.calls == [("tweet", 124), ("tweet", 123)]


async def test_search_x_accepts_authors_without_query():
    reader = FakeReader()
    async with Client(create_mcp_server(reader)) as client:
        result = await client.call_tool("search_x", {"authors": ["https://x.com/alice"]})
    assert result.is_error is False
    assert [item["id"] for item in result.structured_content["posts"]] == ["123"]
    assert ("search", "(from:alice)", 60) in reader.calls


async def test_mcp_validation_domain_errors_and_rate_limit():
    reader = FakeReader()
    async with Client(create_mcp_server(reader, rate_limit=5)) as client:
        no_query = await client.call_tool("search_x", {})
        invalid = await client.call_tool("search_x", {"query": "topic", "authors": ["bad)name"]})
        missing_user = await client.call_tool("get_x_user_posts", {"username": "missing"})
        missing_post = await client.call_tool("get_x_post", {"tweet_id": 999})
        invalid_id = await client.call_tool("get_x_post", {"tweet_id": 0})
        invalid_limit = await client.call_tool("read_x_user", {"user": "alice", "limit": 0})
    assert all(result.is_error for result in [no_query, invalid, missing_user, missing_post, invalid_id, invalid_limit])
    assert "query or authors" in no_query.content[0].text
    assert "not found" in missing_user.content[0].text
    assert "not found" in missing_post.content[0].text
    assert ("search", "topic", 60) not in reader.calls


async def test_legacy_thread_returns_empty_posts_for_missing_anchor():
    async with Client(create_mcp_server(FakeReader())) as client:
        result = await client.call_tool("get_x_thread", {"tweet_id": 999})
    assert result.is_error is False
    assert result.structured_content == {"posts": []}


async def test_mcp_request_budget_is_separate():
    reader = FakeReader()
    async with Client(create_mcp_server(reader, rate_limit=1)) as client:
        first = await client.call_tool("get_x_post", {"tweet_id": 123})
        second = await client.call_tool("get_x_post", {"tweet_id": 123})
    assert first.is_error is False
    assert second.is_error is True
    assert "rate limit" in second.content[0].text.lower()
    assert reader.calls == [("tweet", 123)]
