import importlib


def test_filter_author_thread_keeps_only_same_author_and_conversation():
    thread = importlib.import_module("x_reader.thread")
    filter_author_thread = getattr(thread, "filter_author_thread", None)

    assert filter_author_thread is not None

    items = [
        {
            "id": 1,
            "date": "2026-09-03 19:32:13+00:00",
            "conversationId": 100,
            "user": {"username": "OpenAI"},
        },
        {
            "id": 2,
            "date": "2026-09-03 19:32:14+00:00",
            "conversationId": 100,
            "user": {"username": "OpenAI"},
        },
        {
            "id": 3,
            "date": "2026-09-03 19:32:15+00:00",
            "conversationId": 100,
            "user": {"username": "random_reply_guy"},
        },
        {
            "id": 4,
            "date": "2026-09-03 19:32:16+00:00",
            "conversationId": 999,
            "user": {"username": "OpenAI"},
        },
    ]

    filtered = filter_author_thread(items)

    assert [item["id"] for item in filtered] == [1, 2]
