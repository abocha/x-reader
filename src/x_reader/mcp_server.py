from __future__ import annotations

from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from x_reader.normalize import normalize_tweet
from x_reader.rate_limit import SlidingWindowRateLimiter
from x_reader.reader import TwscrapeReader
from x_reader.search import build_search_query, filter_search_results, validate_authors
from x_reader.thread import filter_author_thread


READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

Limit = Annotated[int, Field(ge=1, le=50)]
TweetId = Annotated[int, Field(gt=0)]
Query = Annotated[str, Field(min_length=1, max_length=200)]


def _validate_username(username: str) -> None:
    try:
        validate_authors([username])
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def _validate_authors(authors: list[str]) -> None:
    if not authors:
        return

    try:
        validate_authors(authors)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def create_mcp_server(
    reader: Any = None,
    rate_limit: int = 60,
    rate_window_seconds: float = 3600,
) -> MCPServer:
    reader = reader or TwscrapeReader()
    limiter = SlidingWindowRateLimiter(
        limit=rate_limit,
        window_seconds=rate_window_seconds,
    )
    mcp = MCPServer("x-reader")

    def enforce_rate_limit() -> None:
        if not limiter.allow("mcp"):
            raise ToolError("Rate limit exceeded")

    @mcp.tool(
        title="Search X",
        description=(
            "Search current public posts on X/Twitter. Use this when the user asks "
            "what people are saying on X/Twitter about a topic, event, person, "
            "product, announcement, rumor, outage, or current discussion."
        ),
        annotations=READ_ONLY,
    )
    async def search_x(
        query: Query,
        authors: list[str] | None = None,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        author_list = authors or []
        _validate_authors(author_list)
        enforce_rate_limit()

        search_query = build_search_query(query, author_list)
        results = await reader.search(search_query, max(20, limit))
        filtered = filter_search_results(
            results,
            authors=author_list,
            limit=limit,
        )

        return {"posts": [normalize_tweet(tweet) for tweet in filtered]}

    @mcp.tool(
        title="Get X user posts",
        description=(
            "Read recent public posts from a specific X/Twitter account. Use this "
            "when the user asks what a person or organization has posted on X/Twitter."
        ),
        annotations=READ_ONLY,
    )
    async def get_x_user_posts(
        username: str,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        _validate_username(username)
        enforce_rate_limit()

        results = await reader.user_posts(username=username, limit=limit)
        if results is None:
            raise ToolError(f"X user not found: {username}")

        return {
            "posts": [normalize_tweet(tweet) for tweet in results[:limit]],
        }

    @mcp.tool(
        title="Get X post",
        description=(
            "Read one public X/Twitter post by its numeric post ID. Use this when "
            "the user asks about a specific X/Twitter post."
        ),
        annotations=READ_ONLY,
    )
    async def get_x_post(tweet_id: TweetId) -> dict[str, Any]:
        enforce_rate_limit()
        result = await reader.tweet(tweet_id=tweet_id)
        if result is None:
            raise ToolError(f"X post not found: {tweet_id}")

        return {"post": normalize_tweet(result)}

    @mcp.tool(
        title="Get X thread",
        description=(
            "Read the author's thread around a specific X/Twitter post. Use this "
            "when the user asks to read the thread, its continuation, or what the "
            "author wrote next."
        ),
        annotations=READ_ONLY,
    )
    async def get_x_thread(
        tweet_id: TweetId,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        enforce_rate_limit()
        results = await reader.thread(
            tweet_id=tweet_id,
            limit=max(20, limit),
        )
        if not results:
            return {"posts": []}

        filtered = filter_author_thread(
            results,
            anchor_tweet_id=tweet_id,
        )
        return {
            "posts": [normalize_tweet(tweet) for tweet in filtered[:limit]],
        }

    return mcp


mcp = create_mcp_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
