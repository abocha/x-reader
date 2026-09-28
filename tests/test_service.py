from datetime import datetime, timezone

import pytest

from x_reader.errors import PostNotFound, UserNotFound
from x_reader.service import XReaderService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def post(post_id, author_id=1, *, date="2026-01-02T00:00:00Z", reply_to=None, repost=None, conversation=100):
    return {
        "id": post_id, "date": date, "rawContent": f"text {post_id}",
        "user": {"id": author_id, "username": "alice" if author_id == 1 else "bob", "displayname": "Name"},
        "conversationId": conversation, "inReplyToTweetId": reply_to,
        "retweetedTweet": repost,
    }


class FakeReader:
    def __init__(self):
        self.profile = {"id": 1, "username": "alice", "pinnedIds": []}
        self.timeline = []
        self.search_items = []
        self.posts = {}
        self.conversation_items = []
        self.reply_items = []
        self.calls = []

    async def user(self, username):
        self.calls.append(("user", username))
        return self.profile if username.lower() == "alice" else None

    async def user_about(self, username):
        return {"account_based_in": "US"}

    async def user_posts_by_id(self, user_id, limit):
        self.calls.append(("user_posts_by_id", user_id, limit))
        return self.timeline

    async def user_posts_and_replies_by_id(self, user_id, limit):
        self.calls.append(("user_posts_and_replies_by_id", user_id, limit))
        return self.timeline

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
        self.calls.append(("tweet_replies", tweet_id, limit))
        return self.reply_items


@pytest.mark.parametrize(
    "include_replies,include_reposts,expected",
    [
        (False, False, ["1"]),
        (True, False, ["2", "1"]),
        (False, True, ["4", "3", "1"]),
        (True, True, ["4", "3", "2", "1"]),
    ],
)
async def test_timeline_classification_and_foreign_provenance(include_replies, include_reposts, expected):
    reader = FakeReader()
    reader.timeline = [
        post(1, date="2026-01-01T00:00:00Z"),
        post(2, reply_to=99, date="2026-01-02T00:00:00Z"),
        post(3, repost=post(30, 2), date="2026-01-03T00:00:00Z"),
        post(4, 2, date="2026-01-04T00:00:00Z"),
    ]
    result = await XReaderService(reader).read_user("@alice", include_replies=include_replies, include_reposts=include_reposts)
    assert [item["id"] for item in result["posts"]] == expected
    kinds = {item["id"]: item["timeline_item_type"] for item in result["posts"]}
    assert kinds == {"1": "post", **({"2": "reply"} if include_replies else {}), **({"3": "repost", "4": "foreign"} if include_reposts else {})}
    if include_reposts:
        foreign = result["posts"][0]
        assert foreign["author"]["id"] == "2"
        assert foreign["is_repost"] is False
        assert foreign["appeared_on_timeline_of"] == {"id": "1", "username": "alice"}
        assert result["posts"][1]["reposted_post"]["id"] == "30"


@pytest.mark.parametrize("include_replies,method", [
    (False, "user_posts_by_id"),
    (True, "user_posts_and_replies_by_id"),
])
async def test_read_user_looks_up_profile_once_and_fetches_timeline_by_id(include_replies, method):
    reader = FakeReader()
    reader.timeline = [post(1)]
    result = await XReaderService(reader).read_user("@alice", include_replies=include_replies)
    assert [item["id"] for item in result["posts"]] == ["1"]
    assert reader.calls == [("user", "alice"), (method, 1, 60)]


async def test_read_user_deduplicates_before_limit_and_keeps_first_item():
    reader = FakeReader()
    duplicate = post(1, date="2026-01-02T00:00:00Z")
    duplicate["rawContent"] = "duplicate copy"
    reader.timeline = [
        post(1, date="2026-01-02T00:00:00Z"),
        duplicate,
        post(2, date="2026-01-01T00:00:00Z"),
    ]

    result = await XReaderService(reader).read_user("alice", limit=2)

    assert [item["id"] for item in result["posts"]] == ["1", "2"]
    assert result["posts"][0]["text"] == "text 1"


async def test_read_user_keeps_multiple_posts_without_ids():
    reader = FakeReader()
    reader.timeline = [post(None), post(None)]

    result = await XReaderService(reader).read_user("alice")

    assert [item["id"] for item in result["posts"]] == [None, None]


async def test_pinned_posts_are_marked_and_sorted_by_creation():
    reader = FakeReader()
    reader.profile["pinnedIds"] = [1]
    reader.timeline = [post(1, date="2020-01-01T00:00:00Z"), post(2, date="2026-01-01T00:00:00Z")]
    result = await XReaderService(reader).read_user("https://x.com/alice", include_about=True)
    assert [item["id"] for item in result["posts"]] == ["2", "1"]
    assert [item["is_pinned"] for item in result["posts"]] == [False, True]
    assert result["about"]["account_based_in"] == "US"


async def test_foreign_repost_remains_foreign_to_requested_user():
    reader = FakeReader()
    reader.timeline = [post(5, 2, repost=post(50, 3))]
    result = await XReaderService(reader).read_user("alice", include_reposts=True)
    item = result["posts"][0]
    assert item["timeline_item_type"] == "foreign"
    assert item["author"]["id"] == "2"
    assert item["is_repost"] is True
    assert item["appeared_on_timeline_of"]["id"] == "1"


@pytest.mark.parametrize("context,expected", [
    ("author_thread", ["100", "101"]),
    ("conversation", ["100", "101", "102"]),
])
async def test_context_from_continuation_keeps_root_and_excludes_anchor(context, expected):
    reader = FakeReader()
    root = post(100, date="2026-01-01T00:00:00Z")
    continuation = post(103, reply_to=101, date="2026-01-04T00:00:00Z")
    reader.posts[103] = continuation
    reader.conversation_items = [
        root, post(101, reply_to=100, date="2026-01-02T00:00:00Z"),
        post(102, 2, reply_to=100, date="2026-01-03T00:00:00Z"),
    ]
    result = await XReaderService(reader).read_post("https://twitter.com/alice/status/103", context=context)
    assert result["post"]["id"] == "103"
    assert result["context"]["type"] == context
    assert [item["id"] for item in result["context"]["posts"]] == expected
    assert ("conversation", 100, 60) in reader.calls


@pytest.mark.parametrize("context", ["author_thread", "conversation"])
async def test_anchor_does_not_consume_context_limit(context):
    reader = FakeReader()
    reader.posts[100] = post(100, date="2026-01-01T00:00:00Z")
    reader.conversation_items = [
        post(100, date="2026-01-01T00:00:00Z"),
        post(101, reply_to=100, date="2026-01-02T00:00:00Z"),
        post(102, reply_to=100, date="2026-01-03T00:00:00Z"),
    ]

    result = await XReaderService(reader).read_post(100, context=context, limit=2)

    assert [item["id"] for item in result["context"]["posts"]] == ["101", "102"]


async def test_parent_context_reads_only_the_direct_parent():
    reader = FakeReader()
    parent = post(100, date="2026-01-01T00:00:00Z")
    reader.posts[100] = parent
    reader.posts[103] = post(103, reply_to=100)

    result = await XReaderService(reader).read_post(103, context="parent")

    assert reader.calls == [("tweet", 103), ("tweet", 100)]
    assert result["context"]["type"] == "parent"
    assert [item["id"] for item in result["context"]["posts"]] == ["100"]
    assert result["context"]["posts"][0]["text"] == parent["rawContent"]


async def test_parent_context_for_non_reply_does_not_fetch_another_post():
    reader = FakeReader()
    reader.posts[103] = post(103)

    result = await XReaderService(reader).read_post(103, context="parent")

    assert reader.calls == [("tweet", 103)]
    assert result["context"] == {"type": "parent", "posts": []}


async def test_parent_context_keeps_target_when_parent_is_missing():
    reader = FakeReader()
    reader.posts[103] = post(103, reply_to=100)

    result = await XReaderService(reader).read_post(103, context="parent")

    assert reader.calls == [("tweet", 103), ("tweet", 100)]
    assert result["post"]["id"] == "103"
    assert result["context"] == {"type": "parent", "posts": []}


async def test_parent_context_excludes_anchor_if_lookup_returns_it():
    reader = FakeReader()
    reader.posts[103] = post(103, reply_to=103)

    result = await XReaderService(reader).read_post(103, context="parent")

    assert reader.calls == [("tweet", 103), ("tweet", 103)]
    assert result["context"] == {"type": "parent", "posts": []}


async def test_replies_only_include_direct_replies():
    reader = FakeReader()
    reader.posts[100] = post(100)
    reader.reply_items = [
        post(100, reply_to=100, date="2026-01-01T00:00:00Z"),
        post(101, 2, reply_to=100, date="2026-01-02T00:00:00Z"),
        post(102, 2, reply_to=101),
    ]
    result = await XReaderService(reader).read_post(100, context="replies", limit=1)
    assert [item["id"] for item in result["context"]["posts"]] == ["101"]
    assert result["post"]["id"] not in [
        item["id"] for item in result["context"]["posts"]
    ]
    assert ("tweet_replies", 100, 40) in reader.calls


@pytest.mark.parametrize("context", ["author_thread", "replies", "conversation"])
async def test_read_post_context_deduplicates_posts(context):
    reader = FakeReader()
    reader.posts[100] = post(100)
    if context == "replies":
        reader.reply_items = [
            post(100, reply_to=100),
            post(101, 2, reply_to=100),
            post(101, 2, reply_to=100),
            post(102, 2, reply_to=101),
        ]
        expected = ["101"]
    else:
        reader.conversation_items = [
            post(100),
            post(101, reply_to=100),
            post(101, reply_to=100),
            post(102, 2, reply_to=100),
        ]
        expected = ["101"] if context == "author_thread" else ["101", "102"]

    result = await XReaderService(reader).read_post(100, context=context)

    assert [item["id"] for item in result["context"]["posts"]] == expected
    assert result["post"]["id"] not in [
        item["id"] for item in result["context"]["posts"]
    ]


@pytest.mark.parametrize("query,authors,upstream", [
    ("topic", None, "topic"),
    (None, ["@alice"], "(from:alice)"),
    ("topic", ["https://x.com/alice"], "(from:alice) (topic)"),
])
async def test_search_forms_and_client_filters(query, authors, upstream):
    reader = FakeReader()
    reader.search_items = [
        post(1, date="2026-01-02T00:00:00Z"),
        post(2, reply_to=99), post(3, repost=post(30, 2)),
        post(4, 2), post(5, date="2025-01-01T00:00:00Z"),
    ]
    result = await XReaderService(reader).search(
        query=query, authors=authors,
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        until=datetime(2026, 1, 3, tzinfo=timezone.utc),
        include_replies=False, include_reposts=False,
    )
    assert [item["id"] for item in result["posts"]] == (["1", "4"] if authors is None else ["1"])
    assert ("search", upstream, 60) in reader.calls


async def test_search_rejects_missing_terms_and_naive_boundaries():
    reader = FakeReader()
    with pytest.raises(ValueError, match="Either query or authors"):
        await XReaderService(reader).search()
    with pytest.raises(ValueError, match="timezone-aware"):
        await XReaderService(reader).search(query="topic", since=datetime(2026, 1, 1))
    assert reader.calls == []


async def test_multi_author_search_has_one_search_and_no_profile_lookups():
    reader = FakeReader()
    reader.search_items = [post(1), post(2, 2), post(3, 3)]
    reader.search_items[1]["user"]["username"] = "BoB"
    reader.search_items[-1]["user"]["username"] = "charlie"
    result = await XReaderService(reader).search(authors=["@alice", "https://x.com/bob"])
    assert [item["id"] for item in result["posts"]] == ["1", "2"]
    assert reader.calls == [("search", "(from:alice OR from:bob)", 60)]


async def test_search_deduplicates_repeated_ids_before_limit():
    reader = FakeReader()
    reader.search_items = [post(1), post(1), post(2)]

    result = await XReaderService(reader).search(query="topic", limit=2)

    assert [item["id"] for item in result["posts"]] == ["1", "2"]


async def test_missing_user_and_post_are_domain_errors():
    reader = FakeReader()
    with pytest.raises(UserNotFound):
        await XReaderService(reader).read_user("missing")
    with pytest.raises(PostNotFound):
        await XReaderService(reader).read_post(999)


async def test_search_projection_preserves_filtered_order_and_reader_calls():
    reader = FakeReader()
    reader.search_items = [
        post(2, reply_to=1, date="2026-01-03T00:00:00Z"),
        post(1, date="2026-01-02T00:00:00Z"),
        post(1, date="2026-01-02T00:00:00Z"),
        post(3, 2, date="2026-01-01T00:00:00Z"),
    ]
    service = XReaderService(reader)
    full = await service.search(query="topic", authors=["alice"], detail="full")
    full_calls = reader.calls[:]
    reader.calls.clear()
    compact = await service.search(query="topic", authors=["alice"], detail="compact")
    assert reader.calls == full_calls == [("search", "(from:alice) (topic)", 60)]
    assert [item["id"] for item in full["posts"]] == ["2", "1"]
    assert [item["id"] for item in compact["posts"]] == ["2", "1"]
    assert "metrics" in full["posts"][0] and "metrics" not in compact["posts"][0]


async def test_user_projection_preserves_pinned_provenance_and_reader_calls():
    reader = FakeReader()
    reader.profile["pinnedIds"] = [1]
    reader.timeline = [
        post(1, date="2026-01-01T00:00:00Z"),
        post(2, 2, date="2026-01-03T00:00:00Z"),
        post(2, 2, date="2026-01-03T00:00:00Z"),
        post(3, reply_to=1, date="2026-01-02T00:00:00Z"),
    ]
    service = XReaderService(reader)
    options = {"include_replies": True, "include_reposts": True}
    full = await service.read_user("alice", detail="full", **options)
    full_calls = reader.calls[:]
    reader.calls.clear()
    compact = await service.read_user("alice", detail="compact", **options)
    assert reader.calls == full_calls == [("user", "alice"), ("user_posts_and_replies_by_id", 1, 60)]
    for result in (full, compact):
        assert [item["id"] for item in result["posts"]] == ["2", "3", "1"]
        assert [item["timeline_item_type"] for item in result["posts"]] == ["foreign", "reply", "post"]
        assert [item["is_pinned"] for item in result["posts"]] == [False, False, True]
        assert result["posts"][0]["appeared_on_timeline_of"] == {"id": "1", "username": "alice"}
    assert "metrics" in full["posts"][0] and "metrics" not in compact["posts"][0]


@pytest.mark.parametrize("context", ["none", "parent", "author_thread", "replies", "conversation"])
async def test_post_projection_covers_anchor_context_and_reader_calls(context):
    reader = FakeReader()
    reader.posts = {100: post(100), 101: post(101, reply_to=100)}
    reader.conversation_items = [post(100), post(101, reply_to=100), post(102, 2, reply_to=100)]
    reader.reply_items = [post(102, 2, reply_to=101)]
    service = XReaderService(reader)
    full = await service.read_post(101, context=context, detail="full")
    full_calls = reader.calls[:]
    reader.calls.clear()
    compact = await service.read_post(101, context=context, detail="compact")
    assert reader.calls == full_calls
    assert compact["post"]["id"] == full["post"]["id"] == "101"
    if context != "none":
        assert [item["id"] for item in compact["context"]["posts"]] == [
            item["id"] for item in full["context"]["posts"]
        ]
    for item in [compact["post"], *compact.get("context", {}).get("posts", [])]:
        assert "metrics" not in item
    for item in [full["post"], *full.get("context", {}).get("posts", [])]:
        assert "metrics" in item
