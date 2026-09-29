def build_search_query(query: str, authors: list[str]) -> str:
    if not authors:
        return query

    author_filter = " OR ".join(f"from:{author}" for author in authors)
    return f"({author_filter}) ({query})"


def filter_search_results(
    results: list[dict],
    authors: list[str],
    limit: int,
) -> list[dict]:
    if not authors:
        return results[:limit]

    allowed = {author.lower() for author in authors}

    filtered = [
        item
        for item in results
        if item["user"]["username"].lower() in allowed
    ]

    return filtered[:limit]


import re

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def validate_authors(authors: list[str]) -> list[str]:
    if not authors:
        raise ValueError("At least one author is required")

    for author in authors:
        if not _USERNAME_RE.fullmatch(author):
            raise ValueError(f"Invalid X username: {author}")

    return authors
