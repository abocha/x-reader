from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from x_reader.errors import PostNotFound, UserNotFound
from x_reader.filters import (
    classify_timeline_item,
    dedupe_by_id,
    exclude_by_id,
    same_author,
    sort_by_created_at,
    timestamp,
)
from x_reader.locators import parse_post_locator, parse_username
from x_reader.normalize import (
    PostDetail,
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
    text_part = f"({query})" if query and author_part else (query or "")
    if author_part and text_part:
        return f"{author_part} {text_part}"
    return author_part or text_part


def _prepare_context_items(
    items: list[dict[str, Any]], anchor_id: int, *, include_anchor: bool
) -> list[dict[str, Any]]:
    items = dedupe_by_id(items)
    if not include_anchor:
        items = exclude_by_id(items, anchor_id)
    return items


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
        detail: PostDetail = "full",
    ) -> dict[str, Any]:
        query = query.strip() if query is not None else None
        if query and len(query) > 200:
            raise ValueError("query must be at most 200 characters")
        author_list = [parse_username(author) for author in (authors or [])]
        if not query and not author_list:
            raise ValueError("Either query or authors must be provided")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if since is not None and (not isinstance(since, datetime) or since.tzinfo is None or since.utcoffset() is None):
            raise ValueError("since must be a timezone-aware datetime")
        if until is not None and (not isinstance(until, datetime) or until.tzinfo is None or until.utcoffset() is None):
            raise ValueError("until must be a timezone-aware datetime")
        if since and until and since > until:
            raise ValueError("since must not be after until")

        fetch_limit = overfetch_limit(limit)

        raw = await self.reader.search(
            _build_search_query(query, author_list),
            fetch_limit,
        )

        allowed_author_names = {username.lower() for username in author_list}

        filtered = []
        for item in raw:
            author = item.get("user") or {}
            author_name = (author.get("username") or "").lower()
            if author_list and author_name not in allowed_author_names:
                continue
            created = timestamp(item.get("date"))
            if since and (created is None or created < since):
                continue
            if until and (created is None or created > until):
                continue
            if not include_replies and item.get("inReplyToTweetId") is not None:
                continue
            if not include_reposts and item.get("retweetedTweet") is not None:
                continue
            filtered.append(item)

        filtered = sort_by_created_at(dedupe_by_id(filtered))[:limit]
        return {"posts": [normalize_tweet(item, detail=detail) for item in filtered]}

    async def read_user(
        self,
        user: str,
        *,
        limit: int = 20,
        include_replies: bool = False,
        include_reposts: bool = False,
        include_about: bool = False,
        detail: PostDetail = "full",
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be at least 1")

        username = parse_username(user)
        profile = await self.reader.user(username)
        if profile is None:
            raise UserNotFound(f"X user not found: {username}")

        user_id = profile.get("id")
        if user_id is None:
            raise ValueError("X user profile is missing its stable ID")
        fetch_limit = overfetch_limit(limit)

        if include_replies:
            raw_items = await self.reader.user_posts_and_replies_by_id(
                user_id, fetch_limit
            )
        else:
            raw_items = await self.reader.user_posts_by_id(user_id, fetch_limit)

        raw_items = _inject_pinned(raw_items, profile.get("pinnedIds") or [])

        kept = []
        timeline_user = {"id": str(user_id), "username": profile.get("username") or username}
        for item in raw_items:
            kind = classify_timeline_item(item, user_id)
            if kind == "reply" and not include_replies:
                continue
            if kind in ("repost", "foreign") and not include_reposts:
                continue
            entry = {**item, "timeline_item_type": kind}
            if kind == "foreign" or not same_author(item, {"user": profile}):
                entry["appeared_on_timeline_of"] = timeline_user
            kept.append(entry)

        kept = sort_by_created_at(dedupe_by_id(kept))[:limit]

        result: dict[str, Any] = {
            "user": normalize_user(profile),
            "posts": [normalize_tweet(item, detail=detail) for item in kept],
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
            "parent",
            "author_thread",
            "replies",
            "conversation",
        ] = "none",
        limit: int = 20,
        detail: PostDetail = "full",
        _include_anchor: bool = False,
    ) -> dict[str, Any]:
        if context not in (
            "none",
            "parent",
            "author_thread",
            "replies",
            "conversation",
        ):
            raise ValueError(f"Unknown context: {context}")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        post_id = parse_post_locator(post)
        anchor = await self.reader.tweet(post_id)
        if anchor is None:
            raise PostNotFound(f"X post not found: {post_id}")

        result = {"post": normalize_tweet(anchor, detail=detail)}
        if context == "none":
            return result

        if context == "parent":
            parent_id = anchor.get("inReplyToTweetId")
            parent = None
            if parent_id is not None:
                try:
                    parent_id = parse_post_locator(parent_id)
                except ValueError:
                    pass
                else:
                    parent = await self.reader.tweet(parent_id)

            parents = exclude_by_id([parent] if parent is not None else [], post_id)
            result["context"] = {
                "type": context,
                "posts": [normalize_tweet(item, detail=detail) for item in parents],
            }
            return result

        fetch_limit = overfetch_limit(limit)

        if context == "author_thread":
            conversation_id = anchor.get("conversationId") or anchor["id"]
            items = await self.reader.conversation(int(conversation_id), fetch_limit)
            if str(anchor.get("id")) not in {str(item.get("id")) for item in items}:
                items = items + [anchor]
            thread = [
                item
                for item in items
                if str(item.get("conversationId") or item.get("id")) == str(conversation_id)
                and same_author(item, anchor)
            ]
            thread = sort_by_created_at(
                _prepare_context_items(
                    thread, post_id, include_anchor=_include_anchor
                ),
                descending=False,
            )[:limit]
            result["context"] = {"type": context, "posts": [normalize_tweet(item, detail=detail) for item in thread]}
            return result

        if context == "replies":
            replies = await self.reader.tweet_replies(post_id, fetch_limit)
            replies = [item for item in replies if str(item.get("inReplyToTweetId")) == str(post_id)]
            replies = sort_by_created_at(
                _prepare_context_items(
                    replies, post_id, include_anchor=_include_anchor
                ),
                descending=False,
            )[:limit]
            result["context"] = {"type": context, "posts": [normalize_tweet(item, detail=detail) for item in replies]}
            return result

        conversation_id = anchor.get("conversationId") or anchor["id"]
        items = await self.reader.conversation(int(conversation_id), fetch_limit)
        if str(anchor.get("id")) not in {str(item.get("id")) for item in items}:
            items = items + [anchor]
        items = [
            item
            for item in items
            if str(item.get("conversationId") or item.get("id")) == str(conversation_id)
        ]
        items = sort_by_created_at(
            _prepare_context_items(items, post_id, include_anchor=_include_anchor),
            descending=False,
        )[:limit]
        result["context"] = {"type": context, "posts": [normalize_tweet(item, detail=detail) for item in items]}
        return result
