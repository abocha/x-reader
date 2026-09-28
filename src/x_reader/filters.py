from datetime import datetime, timezone


def timestamp(value) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def sort_by_created_at(items: list[dict], *, descending: bool = True) -> list[dict]:
    return sorted(
        items,
        key=lambda item: timestamp(item.get("date")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=descending,
    )


def is_own_post(item: dict, requested_user_id: str | int | None) -> bool:
    author_id = (item.get("user") or {}).get("id")
    return author_id is not None and requested_user_id is not None and str(author_id) == str(requested_user_id)


def is_reply(item: dict) -> bool:
    return item.get("inReplyToTweetId") is not None


def is_repost(item: dict) -> bool:
    return item.get("retweetedTweet") is not None


def same_author(item: dict, anchor: dict) -> bool:
    author = anchor.get("user") or {}
    if author.get("id") is not None:
        return is_own_post(item, author["id"])
    username = author.get("username")
    return bool(username) and (item.get("user") or {}).get("username", "").lower() == username.lower()


def classify_timeline_item(item: dict, requested_user_id: str | int | None) -> str:
    if not is_own_post(item, requested_user_id):
        return "foreign"
    if is_repost(item):
        return "repost"
    if is_reply(item):
        return "reply"
    return "post"
