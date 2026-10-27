from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from functools import wraps
from importlib.metadata import version
from math import ceil
from pathlib import Path
from time import monotonic
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from x_reader.errors import PostNotFound, RequestRateLimited, XReaderError
from x_reader.normalize import PostDetail
from x_reader.rate_limit import SlidingWindowRateLimiter
from x_reader.reader import TwscrapeReader
from x_reader.service import XReaderService

logger = logging.getLogger(__name__)


def _server_version() -> str:
    package_version = version("x-reader")
    root = Path(__file__).resolve().parents[2]
    if not (root / "pyproject.toml").is_file() or not (root / ".git").exists():
        return package_version
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root,
            capture_output=True, text=True, check=True, timeout=2,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, check=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return package_version
    return f"{package_version}+git.{revision}" + (".dirty" if dirty else "")


def _tool_failure(error: XReaderError) -> CallToolResult:
    payload = {
        "code": error.code, "category": error.category, "message": str(error),
        "retryable": error.retryable, "retry_after_seconds": error.retry_after_seconds,
        "endpoint": error.endpoint,
    }
    # Keep execution errors inside MCP results. The text copy survives hosts that
    # flatten structuredContent or label every execution error INVALID_ARGUMENT.
    return CallToolResult(
        is_error=True, structured_content={"error": payload},
        content=[TextContent(type="text", text=json.dumps({"error": payload}))],
    )


READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

Limit = Annotated[int, Field(ge=1, le=50)]
TweetId = Annotated[str, Field(pattern=r"^[0-9]{1,20}$")]


def create_mcp_server(
    reader: Any = None,
    rate_limit: int = 60,
    rate_window_seconds: float = 3600,
) -> MCPServer:
    service = XReaderService(reader or TwscrapeReader())
    limiter = SlidingWindowRateLimiter(limit=rate_limit, window_seconds=rate_window_seconds)
    mcp = MCPServer("x-reader", version=_server_version())

    def request(operation):
        @wraps(operation)
        async def wrapped(*args, **kwargs):
            started = monotonic()
            outcome = "success"
            result_count = 0
            try:
                if not limiter.allow("mcp"):
                    outcome = "rate_limited"
                    raise RequestRateLimited("Rate limit exceeded", retry_after_seconds=ceil(rate_window_seconds))
                result = await operation(*args, **kwargs)
                result_count = (
                    len(result.get("posts", []))
                    + int("post" in result)
                    + len(result.get("context", {}).get("posts", []))
                )
                return result
            except ValueError as exc:
                outcome = "validation_error"
                raise ToolError(str(exc)) from exc
            except XReaderError as exc:
                outcome = exc.category
                return _tool_failure(exc)
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except ToolError:
                raise
            except Exception as exc:
                outcome = "internal_error"
                raise ToolError("X request failed unexpectedly. Check server diagnostics.") from exc
            finally:
                logger.info(json.dumps({
                    "event": "x_reader_request",
                    "tool": operation.__name__,
                    "elapsed_ms": round((monotonic() - started) * 1000, 2),
                    "result_count": result_count,
                    "outcome": outcome,
                }))

        return wrapped

    @mcp.tool(
        title="Search X",
        description=(
            "Search current public posts on X/Twitter. Use this when the user asks "
            "what people are saying on X/Twitter about a topic, event, person, "
            "product, announcement, rumor, outage, or current discussion. "
            "Supply a query, authors, or both; authors accept usernames, @handles, and profile URLs. "
            "Ranking recent uses Latest and returns newest first; top preserves X Top order. "
            "since/until require timezones, with until exclusive; these date filters and all "
            "required_terms (case-insensitive substrings in post text) apply locally to a bounded sample. "
            "include_sampling adds query, exclusions, timestamps, and explicit coverage limits. "
            "include_metrics adds lightweight counters without media. "
            "Minimal (default) suits broad discovery and larger result sets; "
            "compact adds structure/provenance; full adds metrics, media, links, cards, and mentions when useful."
        ),
        annotations=READ_ONLY,
    )
    @request
    async def search_x(
        query: str | None = None,
        authors: list[str] | None = None,
        limit: Limit = 20,
        detail: PostDetail = "minimal",
        ranking: Literal["recent", "top"] = "recent",
        since: datetime | None = None,
        until: datetime | None = None,
        include_replies: bool = True,
        include_reposts: bool = True,
        required_terms: list[str] | None = None,
        include_metrics: bool = False,
        include_sampling: bool = False,
    ) -> dict[str, Any]:
        return await service.search(
            query=query, authors=authors, limit=limit, detail=detail,
            ranking=ranking, since=since, until=until,
            include_replies=include_replies, include_reposts=include_reposts,
            required_terms=required_terms, include_metrics=include_metrics,
            include_sampling=include_sampling,
        )

    @mcp.tool(
        title="Get X user posts",
        description="Read recent original public posts from a specific X/Twitter account.",
        annotations=READ_ONLY,
    )
    @request
    async def get_x_user_posts(username: str, limit: Limit = 20) -> dict[str, Any]:
        result = await service.read_user(username, limit=limit)
        return {"posts": result["posts"]}

    @mcp.tool(
        title="Get X post",
        description="Read one public X/Twitter post by its post ID as a decimal string.",
        annotations=READ_ONLY,
    )
    @request
    async def get_x_post(tweet_id: TweetId) -> dict[str, Any]:
        return await service.read_post(tweet_id)

    @mcp.tool(
        title="Get X thread",
        description=(
            "Read the author's thread around a post, using its post ID as a decimal string."
        ),
        annotations=READ_ONLY,
    )
    @request
    async def get_x_thread(tweet_id: TweetId, limit: Limit = 20) -> dict[str, Any]:
        try:
            result = await service.read_post(
                tweet_id,
                context="author_thread",
                limit=limit,
                _include_anchor=True,
            )
        except PostNotFound:
            return {"posts": []}
        return {"posts": result["context"]["posts"]}

    @mcp.tool(
        title="Read X user",
        description=(
            "Read a user's recent public posts and profile, optionally including replies, "
            "reposts, and account details. User accepts a username, @handle, or X/Twitter profile URL. "
            "Minimal (default) suits timeline exploration; compact adds structure/provenance; "
            "full adds metrics, media, links, cards, and mentions when useful. "
            "include_metrics adds counters to minimal/compact without adding media."
        ),
        annotations=READ_ONLY,
    )
    @request
    async def read_x_user(
        user: str,
        limit: Limit = 20,
        include_replies: bool = False,
        include_reposts: bool = False,
        include_about: bool = False,
        detail: PostDetail = "minimal",
        include_metrics: bool = False,
    ) -> dict[str, Any]:
        return await service.read_user(
            user, limit=limit,
            include_replies=include_replies,
            include_reposts=include_reposts,
            include_about=include_about,
            detail=detail, include_metrics=include_metrics,
        )

    @mcp.tool(
        title="Read X post",
        description=(
            "Read a public X/Twitter post with optional direct parent, author thread, "
            "direct replies, or full conversation context. Context accepts none, parent, "
            "author_thread, replies, or conversation. Post accepts a post ID as a decimal "
            "string or X/Twitter post URL. Full (default) suits focused drill-down; "
            "for larger context reads use minimal for discovery or compact for structure/provenance "
            "when rich metadata is unnecessary. include_metrics adds counters without media. "
            "Context is a bounded upstream sample; result count is not conversation completeness. "
            "include_sampling adds retrieval timestamps and context selection counts with unknown completeness."
        ),
        annotations=READ_ONLY,
    )
    @request
    async def read_x_post(
        post: str,
        context: Literal[
            "none",
            "parent",
            "author_thread",
            "replies",
            "conversation",
        ] = "none",
        limit: Limit = 20,
        detail: PostDetail = "full",
        include_metrics: bool = False,
        include_sampling: bool = False,
    ) -> dict[str, Any]:
        return await service.read_post(
            post, context=context, limit=limit, detail=detail, include_metrics=include_metrics,
            include_sampling=include_sampling,
        )

    return mcp


mcp = create_mcp_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
