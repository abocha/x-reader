from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

PostDetail = Literal["compact", "full"]


def _to_iso_from_msec(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None

    if not isinstance(value, (int, float, str)):
        return None

    try:
        msec = float(value)
    except (OverflowError, ValueError):
        return None

    if msec <= 0:
        return None

    try:
        moment = datetime.fromtimestamp(msec / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None

    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _iso(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _tweet_links(tweet: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"url": link.get("url"), "text": link.get("text")}
        for link in (tweet.get("links") or [])
        if isinstance(link, dict)
    ]


def _nested_tweet_preview(
    tweet: dict[str, Any] | None, *, detail: PostDetail
) -> dict[str, Any] | None:
    if not isinstance(tweet, dict) or not tweet:
        return None

    user = tweet.get("user") or {}

    result = {
        "id": _str_or_none(tweet.get("id")),
        "url": tweet.get("url"),
        "created_at": _iso(tweet.get("date")),
        "text": tweet.get("rawContent"),
        "author": {
            "id": _str_or_none(user.get("id")),
            "username": user.get("username"),
            "name": user.get("displayname"),
        },
    }
    if detail == "full":
        result["links"] = _tweet_links(tweet)
        result["media"] = tweet.get("media") or {}
    return result


def normalize_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None

    return {
        "id": _str_or_none(user.get("id")),
        "username": user.get("username"),
        "name": user.get("displayname"),
        "description": user.get("rawDescription"),
        "created_at": _iso(user.get("created")),
        "followers": user.get("followersCount"),
        "following": user.get("friendsCount"),
        "posts_count": user.get("statusesCount"),
        "location": user.get("location"),
        "verified": user.get("verified"),
        "blue_verified": user.get("blue"),
        "url": f"https://x.com/{user.get('username')}"
        if user.get("username")
        else None,
    }


def normalize_about(about: dict[str, Any] | None) -> dict[str, Any] | None:
    if not about:
        return None

    return {
        "account_based_in": about.get("account_based_in"),
        "location_accurate": about.get("location_accurate"),
        "affiliate_username": about.get("affiliate_username"),
        "username_changes": about.get("username_changes"),
        "username_last_changed_at": _to_iso_from_msec(
            about.get("username_last_changed_at")
        ),
        "identity_verified": about.get("is_identity_verified"),
        "verified_since": _to_iso_from_msec(about.get("verified_since_msec")),
    }


def normalize_tweet(
    tweet: dict[str, Any], *, detail: PostDetail = "full", nested: bool = False
) -> dict[str, Any]:
    user = tweet.get("user") or {}

    if tweet.get("isQuoteStatus") is not None:
        is_quote = bool(tweet.get("isQuoteStatus"))
    else:
        is_quote = tweet.get("quotedTweet") is not None

    result = {
        "id": _str_or_none(tweet.get("id")),
        "url": tweet.get("url"),
        "created_at": _iso(tweet.get("date")),
        "text": tweet.get("rawContent"),
        "author": {
            "id": _str_or_none(user.get("id")),
            "username": user.get("username"),
            "name": user.get("displayname"),
        },
        "is_reply": tweet.get("inReplyToTweetId") is not None,
        "is_repost": tweet.get("retweetedTweet") is not None,
        "is_quote": is_quote,
        "is_pinned": bool(tweet.get("is_pinned", False)),
        "conversation_id": _str_or_none(tweet.get("conversationId")),
        "reply_to_id": _str_or_none(tweet.get("inReplyToTweetId")),
        "metrics": {
            "replies": tweet.get("replyCount"),
            "reposts": tweet.get("retweetCount"),
            "likes": tweet.get("likeCount"),
            "quotes": tweet.get("quoteCount"),
            "bookmarks": tweet.get("bookmarkedCount"),
            "views": tweet.get("viewCount"),
        },
        "links": _tweet_links(tweet),
        "media": tweet.get("media") or {},
        "lang": tweet.get("lang"),
        "mentions": [
            {"username": mention.get("username"), "id": _str_or_none(mention.get("id"))}
            for mention in (tweet.get("mentionedUsers") or [])
            if isinstance(mention, dict)
        ],
        "hashtags": [
            str(hashtag)
            for hashtag in (tweet.get("hashtags") or [])
            if hashtag is not None
        ],
        "possibly_sensitive": tweet.get("possibly_sensitive"),
        "card": tweet.get("card"),
        "quoted_post": None,
        "reposted_post": None,
    }

    if detail == "compact":
        for field in ("metrics", "links", "media", "mentions", "hashtags", "possibly_sensitive", "card"):
            del result[field]

    if tweet.get("timeline_item_type") is not None:
        result["timeline_item_type"] = tweet["timeline_item_type"]
    if tweet.get("appeared_on_timeline_of") is not None:
        result["appeared_on_timeline_of"] = tweet["appeared_on_timeline_of"]

    if not nested:
        result["quoted_post"] = _nested_tweet_preview(tweet.get("quotedTweet"), detail=detail)
        result["reposted_post"] = _nested_tweet_preview(tweet.get("retweetedTweet"), detail=detail)

    return result
