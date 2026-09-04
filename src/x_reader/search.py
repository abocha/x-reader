def build_search_query(query: str, authors: list[str]) -> str:
    author_filter = " OR ".join(f"from:{author}" for author in authors)
    return f"({author_filter}) ({query})"


def filter_search_results(
    results: list[dict],
    authors: list[str],
    limit: int,
) -> list[dict]:
    allowed = {author.lower() for author in authors}

    filtered = [
        item
        for item in results
        if item["user"]["username"].lower() in allowed
    ]

    return filtered[:limit]
