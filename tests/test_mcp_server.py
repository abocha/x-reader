from __future__ import annotations

import importlib
from typing import Any

import pytest
from mcp import Client

from x_reader.normalize import normalize_tweet

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def tweet(
    tweet_id: int,
    *,
    username: str = "OpenAI",
    text: str = "Test post",
    date: str = "2026-09-05T00:00:00Z",
    conversation_id: int | None = None,
) -> dict[str, Any]:
    return {
        "id": tweet_id,
        "url": f"https://x.com/{username}/status/{tweet_id}",
        "date": date,
        "rawContent": text,
        "user": {
            "username": username,
            "displayname": username,
        },
        "replyCount": 1,
        "retweetCount": 2,
        "likeCount": 3,
        "quoteCount": 4,
        "bookmarkedCount": 5,
        "viewCount": 6,
        "conversationId": conversation_id or tweet_id,
        "inReplyToTweetId": None,
        "links": [],
        "media": {
            "photos": [],
            "videos": [],
            "animated": [],
        },
    }


class FakeReader:
    def __init__(self) -> None:
        self.search_results: list[dict] = []
        self.user_results: list[dict] | None = []
        self.tweet_result: dict | None = None
        self.thread_results: list[dict] = []
        self.calls: list[tuple] = []

    async def search(self, query: str, limit: int) -> list[dict]:
        self.calls.append(("search", query, limit))
        return self.search_results

    async def user_posts(self, username: str, limit: int) -> list[dict] | None:
        self.calls.append(("user_posts", username, limit))
        return self.user_results

    async def tweet(self, tweet_id: int) -> dict | None:
        self.calls.append(("tweet", tweet_id))
        return self.tweet_result

    async def thread(self, tweet_id: int, limit: int) -> list[dict]:
        self.calls.append(("thread", tweet_id, limit))
        return self.thread_results


def build_server(reader: FakeReader):
    module = importlib.import_module("x_reader.mcp_server")
    return module.create_mcp_server(reader)


async def test_lists_four_read_only_x_tools():
    reader = FakeReader()

    async with Client(build_server(reader)) as client:
        result = await client.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert set(tools) == {
        "search_x",
        "get_x_user_posts",
        "get_x_post",
        "get_x_thread",
    }

    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is True

    assert "what people" in (tools["search_x"].description or "").lower()
    assert "x/twitter" in (tools["search_x"].description or "").lower()


async def test_search_x_builds_author_query_filters_and_normalizes():
    reader = FakeReader()
    allowed = tweet(1, username="OpenAI", text="Astra rollout")
    unrelated = tweet(2, username="someone_else", text="Astra rumor")
    reader.search_results = [allowed, unrelated]

    async with Client(build_server(reader)) as client:
        result = await client.call_tool(
            "search_x",
            {"query": "Astra", "authors": ["OpenAI"], "limit": 5},
        )

    assert result.is_error is False
    assert result.structured_content == {"posts": [normalize_tweet(allowed)]}
    assert reader.calls == [("search", "(from:OpenAI) (Astra)", 20)]


async def test_search_x_rejects_invalid_limit_before_reader_call():
    reader = FakeReader()

    async with Client(build_server(reader)) as client:
        result = await client.call_tool(
            "search_x",
            {"query": "Astra", "limit": 0},
        )

    assert result.is_error is True
    assert "limit" in result.content[0].text.lower()
    assert reader.calls == []


async def test_get_x_user_posts_returns_normalized_posts():
    reader = FakeReader()
    post = tweet(10, username="OpenAI")
    reader.user_results = [post]

    async with Client(build_server(reader)) as client:
        result = await client.call_tool(
            "get_x_user_posts",
            {"username": "OpenAI", "limit": 3},
        )

    assert result.is_error is False
    assert result.structured_content == {"posts": [normalize_tweet(post)]}
    assert reader.calls == [("user_posts", "OpenAI", 3)]


async def test_get_x_user_posts_reports_missing_user():
    reader = FakeReader()
    reader.user_results = None

    async with Client(build_server(reader)) as client:
        result = await client.call_tool(
            "get_x_user_posts",
            {"username": "missing_user"},
        )

    assert result.is_error is True
    assert "not found" in result.content[0].text.lower()


async def test_get_x_post_returns_normalized_post():
    reader = FakeReader()
    post = tweet(42)
    reader.tweet_result = post

    async with Client(build_server(reader)) as client:
        result = await client.call_tool("get_x_post", {"tweet_id": 42})

    assert result.is_error is False
    assert result.structured_content == {"post": normalize_tweet(post)}
    assert reader.calls == [("tweet", 42)]


async def test_get_x_post_rejects_non_positive_id():
    reader = FakeReader()

    async with Client(build_server(reader)) as client:
        result = await client.call_tool("get_x_post", {"tweet_id": 0})

    assert result.is_error is True
    assert "tweet_id" in result.content[0].text
    assert reader.calls == []


async def test_get_x_thread_filters_to_root_author_and_sorts():
    reader = FakeReader()
    root = tweet(100, date="2026-09-05T00:00:00Z", conversation_id=100)
    other_author = tweet(
        101,
        username="someone_else",
        date="2026-09-05T00:01:00Z",
        conversation_id=100,
    )
    continuation = tweet(
        102,
        date="2026-09-05T00:02:00Z",
        conversation_id=100,
    )
    reader.thread_results = [root, continuation, other_author]

    async with Client(build_server(reader)) as client:
        result = await client.call_tool(
            "get_x_thread",
            {"tweet_id": 100, "limit": 10},
        )

    assert result.is_error is False
    assert [post["id"] for post in result.structured_content["posts"]] == ["100", "102"]
    assert reader.calls == [("thread", 100, 20)]


async def test_get_x_thread_returns_empty_posts_for_missing_thread():
    reader = FakeReader()
    reader.thread_results = []

    async with Client(build_server(reader)) as client:
        result = await client.call_tool("get_x_thread", {"tweet_id": 999})

    assert result.is_error is False
    assert result.structured_content == {"posts": []}
