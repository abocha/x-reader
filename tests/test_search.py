import importlib


def test_build_search_query_adds_from_filters():
    search = importlib.import_module("x_reader.search")
    build_search_query = getattr(search, "build_search_query", None)

    assert build_search_query is not None

    result = build_search_query(
        query="Astra OR GPT-6",
        authors=["OpenAI", "OpenAIDevs", "sama"],
    )

    assert result == (
        "(from:OpenAI OR from:OpenAIDevs OR from:sama) "
        "(Astra OR GPT-6)"
    )


def test_filter_search_results_enforces_authors_and_limit():
    search = importlib.import_module("x_reader.search")
    filter_search_results = getattr(search, "filter_search_results", None)

    assert filter_search_results is not None

    results = [
        {"id": 1, "user": {"username": "OpenAI"}},
        {"id": 2, "user": {"username": "sama"}},
        {"id": 3, "user": {"username": "EgeErdil2"}},
        {"id": 4, "user": {"username": "OpenAIDevs"}},
    ]

    filtered = filter_search_results(
        results,
        authors=["OpenAI", "OpenAIDevs", "sama"],
        limit=2,
    )

    assert [item["id"] for item in filtered] == [1, 2]
