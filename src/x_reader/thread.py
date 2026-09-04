def filter_author_thread(items: list[dict]) -> list[dict]:
    root = items[0]
    root_author = root["user"]["username"].lower()
    conversation_id = root["conversationId"]

    filtered = [
        item
        for item in items
        if item["conversationId"] == conversation_id
        and item["user"]["username"].lower() == root_author
    ]

    return sorted(filtered, key=lambda item: item["date"])
