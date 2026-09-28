from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from x_reader.errors import PostNotFound, UserNotFound
from x_reader.rate_limit import SlidingWindowRateLimiter
from x_reader.reader import TwscrapeReader
from x_reader.service import XReaderService


READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

Limit = Annotated[int, Field(ge=1, le=50)]
TweetId = Annotated[int, Field(gt=0)]


def create_mcp_server(
    reader: Any = None,
    rate_limit: int = 60,
    rate_window_seconds: float = 3600,
) -> MCPServer:
    service = XReaderService(reader or TwscrapeReader())
    limiter = SlidingWindowRateLimiter(limit=rate_limit, window_seconds=rate_window_seconds)
    mcp = MCPServer("x-reader")

    def enforce_rate_limit():
        if not limiter.allow("mcp"):
            raise ToolError("Rate limit exceeded")

    async def call(operation, *args, **kwargs):
        enforce_rate_limit()
        try:
            return await operation(*args, **kwargs)
        except (ValueError, UserNotFound, PostNotFound) as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        title="Search X",
        description=(
            "Search current public posts on X/Twitter. Use this when the user asks "
            "what people are saying on X/Twitter about a topic, event, person, "
            "product, announcement, rumor, outage, or current discussion. "
            "Supply a query, authors, or both; authors accept usernames, @handles, and profile URLs."
        ),
        annotations=READ_ONLY,
    )
    async def search_x(
        query: str | None = None,
        authors: list[str] | None = None,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        return await call(service.search, query=query, authors=authors, limit=limit)

    @mcp.tool(
        title="Get X user posts",
        description="Read recent original public posts from a specific X/Twitter account.",
        annotations=READ_ONLY,
    )
    async def get_x_user_posts(username: str, limit: Limit = 20) -> dict[str, Any]:
        result = await call(service.read_user, username, limit=limit)
        return {"posts": result["posts"]}

    @mcp.tool(
        title="Get X post",
        description="Read one public X/Twitter post by its numeric post ID.",
        annotations=READ_ONLY,
    )
    async def get_x_post(tweet_id: TweetId) -> dict[str, Any]:
        return await call(service.read_post, tweet_id)

    @mcp.tool(
        title="Get X thread",
        description="Read the author's thread around a specific X/Twitter post.",
        annotations=READ_ONLY,
    )
    async def get_x_thread(tweet_id: TweetId, limit: Limit = 20) -> dict[str, Any]:
        enforce_rate_limit()
        try:
            result = await service.read_post(
                tweet_id,
                context="author_thread",
                limit=limit,
                _include_anchor=True,
            )
        except PostNotFound:
            return {"posts": []}
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return {"posts": result["context"]["posts"]}

    @mcp.tool(
        title="Read X user",
        description=(
            "Read a user's recent public posts and profile, optionally including replies, "
            "reposts, and account details. User accepts a username, @handle, or X/Twitter profile URL."
        ),
        annotations=READ_ONLY,
    )
    async def read_x_user(
        user: str,
        limit: Limit = 20,
        include_replies: bool = False,
        include_reposts: bool = False,
        include_about: bool = False,
    ) -> dict[str, Any]:
        return await call(
            service.read_user, user, limit=limit,
            include_replies=include_replies,
            include_reposts=include_reposts,
            include_about=include_about,
        )

    @mcp.tool(
        title="Read X post",
        description=(
            "Read a public X/Twitter post with optional direct parent, author thread, "
            "direct replies, or full conversation context. Context accepts none, parent, "
            "author_thread, replies, or conversation. Post accepts a numeric ID or "
            "X/Twitter post URL."
        ),
        annotations=READ_ONLY,
    )
    async def read_x_post(
        post: str | int,
        context: Literal[
            "none",
            "parent",
            "author_thread",
            "replies",
            "conversation",
        ] = "none",
        limit: Limit = 20,
    ) -> dict[str, Any]:
        return await call(service.read_post, post, context=context, limit=limit)

    return mcp


mcp = create_mcp_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
