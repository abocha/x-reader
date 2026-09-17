from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from x_reader.errors import PostNotFound, UserNotFound
from x_reader.filters import (
    classify_timeline_item,
    sort_by_created_at,
    same_author,
    timestamp,
)
from x_reader.locators import parse_post_locator, parse_username
from x_reader.normalize import (
    normalize_about,
    normalize_tweet,
    normalize_user,
)


def overfetch_limit(limit: int) -> int:
    return min(max(limit * 3, 40), 200)


def _inject_pinned(
    items: list[dict[str, Any]], pinned_ids: list[Any]
) -> list[dict[str, Any]]:
    if not pinned_ids:
        return items

    pinned = {str(pid) for pid in pinned_ids}
    return [
        {**item, "is_pinned": str(item.get("id")) in pinned}
        for item in items
    ]


def _build_search_query(
    query: str | None,
    authors: list[str],
) -> str:
    author_part = ""
    if authors:
        author_part = "(" + " OR ".join(f"from:{a}" for a in authors) + ")"
    text_part = f"({query})" if query else ""
    if author_part and text_part:
        return f"{author_part} {text_part}"
    return author_part or text_part


class XReaderService:
    def __init__(self, reader: Any) -> None:
        self.reader = reader

    async def search(
        self,
        *,
        query: str | None = None,
        authors: list[str] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        include_replies: bool = True,
        include_reposts: bool = True,
        limit: int = 20,
    ) -> dict[str, Any]:
        if not query and not authors:
            raise ValueError("Either query or authors must be provided")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        author_list = [a.lstrip("@") for a in (authors or [])]
        fetch_limit = max(limit * 2, 40)

        raw = await self.reader.search(
            _build_search_query(query, author_list),
            fetch_limit,
        )

        author_ids = set()
        if author_list:
            for username in author_list:
                user = await self.reader.user(username)
                if user:
                    author_ids.add(str(user["id"]))

        filtered = []
        for item in raw:
            author_id = str((item.get("user") or {}).get("id") or "")
            if author_ids and author_id not in author_ids:
                continue
            created = timestamp(item.get("date"))
            if since and created and created < since:
                continue
            if until and created and created > until:
                continue
            if not include_replies and item.get("inReplyToTweetId") is not None:
                continue
            if not include_reposts and item.get("retweetedTweet") is not None:
                continue
            filtered.append(item)

        filtered = sort_by_created_at(filtered)[:limit]
        return {"posts": [normalize_tweet(item) for item in filtered]}

    async def read_user(
        self,
        user: str,
        *,
        limit: int = 20,
        include_replies: bool = False,
        include_reposts: bool = False,
        include_about: bool = False,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        username = parse_username(user)
        profile = await self.reader.user(username)
        if profile is None:
            raise UserNotFound(f"X user not found: {username}")

        user_id = profile["id"]
        fetch_limit = overfetch_limit(limit)

        if include_replies:
            raw_items = await self.reader.user_posts_and_replies(
                username, fetch_limit
            )
        else:
            raw_items = await self.reader.user_posts(username, fetch_limit)

        if raw_items is None:
            raise UserNotFound(f"X user not found: {username}")

        raw_items = _inject_pinned(raw_items, profile.get("pinnedIds") or [])

        kept = []
        for item in raw_items:
            kind = classify_timeline_item(item, user_id)
            if kind == "post":
                kept.append(item)
            elif kind == "reply" and include_replies:
                kept.append(item)
            elif kind == "repost" and include_reposts:
                kept.append(item)
            elif kind == "foreign" and include_reposts:
                item = {**item, "is_foreign_timeline_item": True}
                kept.append(item)

        kept = sort_by_created_at(kept)[:limit]

        result: dict[str, Any] = {
            "user": normalize_user(profile),
            "posts": [normalize_tweet(item) for item in kept],
        }

        if include_about:
            about = await self.reader.user_about(username)
            result["about"] = normalize_about(about)

        return result

    async def read_post(
        self,
        post: str | int,
        *,
        context: Literal[
            "none",
            "author_thread",
            "replies",
            "conversation",
        ] = "none",
        limit: int = 20,
    ) -> dict[str, Any]:
        if context not in ("none", "author_thread", "replies", "conversation"):
            raise ValueError(f"Unknown context: {context}")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        post_id = parse_post_locator(post)
        anchor = await self.reader.tweet(post_id)
        if anchor is None:
            raise PostNotFound(f"X post not found: {post_id}")

        if context == "none":
            return {"post": normalize_tweet(anchor)}

        fetch_limit = overfetch_limit(limit)

        if context == "author_thread":
            conversation_id = anchor.get("conversationId") or anchor["id"]
            items = await self.reader.conversation(int(conversation_id), fetch_limit)
            if anchor.get("id") not in {item.get("id") for item in items}:
                items = items + [anchor]
            author = anchor.get("user") or {}
            thread = [
                item
                for item in items
                if item.get("conversationId") == conversation_id
                and same_author(item, anchor)
            ]
            thread = sort_by_created_at(thread, descending=False)[:limit]
            return {"posts": [normalize_tweet(item) for item in thread]}

        if context == "replies":
            replies = await self.reader.tweet_replies(post_id, fetch_limit)
            replies = sort_by_created_at(replies, descending=False)[:limit]
            return {"posts": [normalize_tweet(item) for item in replies]}

        items = await self.reader.conversation(post_id, fetch_limit)
        if anchor.get("id") not in {item.get("id") for item in items}:
            items = items + [anchor]
        conversation_id = anchor.get("conversationId") or anchor["id"]
        items = [
            item
            for item in items
            if item.get("conversationId") == conversation_id
        ]
        items = sort_by_created_at(items, descending=False)[:limit]
        return {"posts": [normalize_tweet(item) for item in items]}
