from __future__ import annotations

from datetime import UTC, datetime
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


class XReaderService:
    def __init__(self, reader: Any) -> None:
        self.reader = reader

    async def search(
        self,
        *,
        query: str | None = None,
        authors: list[str] | None = None,
        limit: int = 20,
        detail: PostDetail = "full",
        ranking: Literal["recent", "top"] = "recent",
        since: datetime | None = None,
        until: datetime | None = None,
        include_replies: bool = True,
        include_reposts: bool = True,
        required_terms: list[str] | None = None,
        include_metrics: bool = False,
        include_sampling: bool = False,
    ) -> dict[str, Any]:
        query = query.strip() if query is not None else None
        if query and len(query) > 200:
            raise ValueError("query must be at most 200 characters")
        author_list = [parse_username(author) for author in (authors or [])]
        if not query and not author_list:
            raise ValueError("Either query or authors must be provided")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if ranking not in ("recent", "top"):
            raise ValueError("ranking must be recent or top")
        for name, bound in (("since", since), ("until", until)):
            if bound is not None and (not isinstance(bound, datetime) or bound.tzinfo is None or bound.utcoffset() is None):
                raise ValueError(f"{name} must be a timezone-aware datetime")
        if since and until and since >= until:
            raise ValueError("since must be before until")
        if required_terms is not None and (
            len(required_terms) > 10
            or any(not isinstance(term, str) or not term.strip() or len(term) > 200 for term in required_terms)
        ):
            raise ValueError("required_terms must contain at most 10 nonempty phrases of at most 200 characters")
        terms = [term.strip().casefold() for term in (required_terms or [])]
        fetch_limit = overfetch_limit(limit)
        upstream_query = _build_search_query(query, author_list)
        if ranking == "recent":
            raw = await self.reader.search(upstream_query, fetch_limit)
        else:
            raw = await self.reader.search(upstream_query, fetch_limit, ranking=ranking)
        retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        allowed_author_names = {username.lower() for username in author_list}
        filtered = []
        exclusions = []
        for item in raw:
            reason = None
            author_name = ((item.get("user") or {}).get("username") or "").lower()
            created = timestamp(item.get("date"))
            if author_list and author_name not in allowed_author_names:
                reason = "author"
            elif since and (created is None or created < since):
                reason = "since"
            elif until and (created is None or created >= until):
                reason = "until"
            elif not include_replies and item.get("inReplyToTweetId") is not None:
                reason = "reply"
            elif not include_reposts and item.get("retweetedTweet") is not None:
                reason = "repost"
            elif terms and not all(term in (item.get("rawContent") or "").casefold() for term in terms):
                reason = "required_terms"
            if reason is None:
                filtered.append(item)
            elif include_sampling:
                exclusions.append({"id": str(item["id"]) if item.get("id") is not None else None, "reason": reason})
        unique = dedupe_by_id(filtered)
        if ranking == "recent":
            unique = sort_by_created_at(unique)
        selected = unique[:limit]
        result: dict[str, Any] = {
            "posts": [normalize_tweet(item, detail=detail, include_metrics=include_metrics) for item in selected],
        }
        if include_sampling:
            result["sampling"] = {
                "retrieved_at": retrieved_at,
                "query_sent": upstream_query,
                "upstream_product": "Latest" if ranking == "recent" else "Top",
                "returned_order": "created_at_desc" if ranking == "recent" else "upstream_order",
                "criteria": {
                    "authors": author_list, "since": since.isoformat() if since else None,
                    "until_exclusive": until.isoformat() if until else None,
                    "include_replies": include_replies, "include_reposts": include_reposts,
                    "required_terms": terms, "required_terms_match": "casefold_substrings_in_post_text",
                },
                "requested_limit": limit, "upstream_limit": fetch_limit,
                "fetched_count": len(raw), "excluded_count": len(exclusions),
                "duplicate_count": len(filtered) - len(unique), "eligible_count": len(unique),
                "returned_count": len(selected), "omitted_by_limit": max(0, len(unique) - limit),
                "exclusions": exclusions,
                "coverage": "bounded_upstream_sample", "total_matching": None,
                "has_more": None,
                "limitations": [
                    "X controls query matching and upstream selection; no exact or semantic guarantee.",
                    "Date and phrase filters apply locally to the fetched sample, not all historical matches.",
                    "Fewer results than requested does not establish completeness or representativeness.",
                ],
            }
        return result

    async def read_user(
        self,
        user: str,
        *,
        limit: int = 20,
        include_replies: bool = False,
        include_reposts: bool = False,
        include_about: bool = False,
        detail: PostDetail = "full",
        include_metrics: bool = False,
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
            "posts": [normalize_tweet(item, detail=detail, include_metrics=include_metrics) for item in kept],
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
        include_metrics: bool = False,
        include_sampling: bool = False,
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

        anchor_retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        result: dict[str, Any] = {"post": normalize_tweet(anchor, detail=detail, include_metrics=include_metrics)}
        raw = []
        items = []
        injected_count = 0
        upstream_limit = 0
        if context == "parent":
            parent_id = anchor.get("inReplyToTweetId")
            if parent_id is not None:
                try:
                    parent_id = parse_post_locator(parent_id)
                except ValueError:
                    pass
                else:
                    upstream_limit = 1
                    parent = await self.reader.tweet(parent_id)
                    raw = [parent] if parent is not None else []
            items = raw
        elif context == "replies":
            upstream_limit = overfetch_limit(limit)
            raw = await self.reader.tweet_replies(post_id, upstream_limit)
            items = [item for item in raw if str(item.get("inReplyToTweetId")) == str(post_id)]
        elif context in ("author_thread", "conversation"):
            upstream_limit = overfetch_limit(limit)
            conversation_id = anchor.get("conversationId") or anchor["id"]
            raw = await self.reader.conversation(int(conversation_id), upstream_limit)
            items = raw
            if str(anchor.get("id")) not in {str(item.get("id")) for item in items}:
                items = items + [anchor]
                injected_count = 1
            items = [
                item for item in items
                if str(item.get("conversationId") or item.get("id")) == str(conversation_id)
            ]
            if context == "author_thread":
                items = [item for item in items if same_author(item, anchor)]
        retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        filtered_out_count = len(raw) + injected_count - len(items)
        unique = dedupe_by_id(items)
        eligible = unique if _include_anchor and context != "parent" else exclude_by_id(unique, post_id)
        selected = sort_by_created_at(eligible, descending=False)[:limit]
        if context != "none":
            result["context"] = {
                "type": context,
                "posts": [normalize_tweet(item, detail=detail, include_metrics=include_metrics) for item in selected],
            }
        if include_sampling:
            result["sampling"] = {
                "retrieved_at": retrieved_at, "anchor_retrieved_at": anchor_retrieved_at,
                "context": context, "requested_limit": limit, "upstream_limit": upstream_limit,
                "fetched_count": len(raw), "anchor_injected_count": injected_count,
                "filtered_out_count": filtered_out_count,
                "duplicate_count": len(items) - len(unique),
                "anchor_excluded_count": len(unique) - len(eligible),
                "eligible_count": len(eligible), "returned_count": len(selected),
                "omitted_by_limit": max(0, len(eligible) - limit),
                "returned_order": (
                    "none" if context == "none" else "direct_parent" if context == "parent"
                    else "created_at_asc_within_upstream_sample"
                ),
                "coverage": (
                    "single_post_lookup" if context == "none" else "direct_parent_lookup" if context == "parent"
                    else "bounded_upstream_sample"
                ),
                "total_matching": None, "has_more": None,
                "limitations": [
                    "Counts describe context posts only; the anchor is returned separately.",
                    "X selects the context sample before local filtering and ordering; completeness is unknown.",
                    "Retrieval timestamps mark fetch completion, not exact or atomic metric measurement times.",
                ],
            }
        return result
