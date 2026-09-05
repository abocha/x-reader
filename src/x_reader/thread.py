def filter_author_thread(
    items: list[dict],
    anchor_tweet_id: int | None = None,
) -> list[dict]:
    if not items:
        return []

    anchor = items[0]
    if anchor_tweet_id is not None:
        anchor = next(
            (
                item
                for item in items
                if str(item["id"]) == str(anchor_tweet_id)
            ),
            anchor,
        )

    anchor_author = anchor["user"]["username"].lower()
    conversation_id = anchor["conversationId"]

    filtered = [
        item
        for item in items
        if item["conversationId"] == conversation_id
        and item["user"]["username"].lower() == anchor_author
    ]

    return sorted(filtered, key=lambda item: item["date"])
