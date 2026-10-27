"""Read-only deployment checks against a real stdio MCP process."""

import argparse
import asyncio
import json
import os
import re
import sys
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters


class VerificationError(Exception):
    pass


async def verify_deployment(
    client: Client, expected_commit: str, post_id: str
) -> dict[str, Any]:
    info = client.server_info
    if info is None or info.name != "x-reader":
        raise VerificationError("The process did not identify itself as x-reader.")
    if info.version.partition("+git.")[2] != expected_commit:
        raise VerificationError(
            "Server revision differs from the expected commit, is dirty, or is unavailable."
        )

    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    expected_tools = {
        "search_x", "get_x_user_posts", "get_x_post", "get_x_thread",
        "read_x_user", "read_x_post",
    }
    if set(tools) != expected_tools:
        raise VerificationError("Server must expose exactly the six x-reader tools.")
    for tool in tools.values():
        if tool.annotations is None or tool.annotations.read_only_hint is not True:
            raise VerificationError("A tool is missing its read-only annotation.")
    for name, parameter in (
        ("get_x_post", "tweet_id"), ("get_x_thread", "tweet_id"),
        ("read_x_post", "post"),
    ):
        schema = tools[name].input_schema.get("properties", {}).get(parameter, {})
        if schema.get("type") != "string" or "anyOf" in schema or "oneOf" in schema:
            raise VerificationError(f"{name} must require a string post locator.")
        if name != "read_x_post" and schema.get("pattern") != r"^[0-9]{1,20}$":
            raise VerificationError(f"{name} must constrain post IDs to decimal strings.")

    response = await client.call_tool("get_x_post", {"tweet_id": post_id})
    if response.is_error:
        raise VerificationError("The live post read failed. Check server diagnostics.")
    post = (response.structured_content or {}).get("post")
    if not isinstance(post, dict) or post.get("id") != post_id:
        raise VerificationError("The returned post ID did not match the exact input string.")
    return {
        "status": "ok", "server_version": info.version,
        "commit": expected_commit, "tools": sorted(tools), "verified_post_id": post_id,
    }


async def _run(command: list[str], expected_commit: str, post_id: str) -> dict[str, Any]:
    async with asyncio.timeout(90):
        async with Client(
            StdioServerParameters(command=command[0], args=command[1:], env=os.environ.copy()),
            read_timeout_seconds=65,
        ) as client:
            return await verify_deployment(client, expected_commit, post_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True, help="Expected full Git commit SHA")
    parser.add_argument("--post-id", required=True, help="Existing public post ID above 2^53-1")
    parser.add_argument(
        "--command", nargs=argparse.REMAINDER,
        default=[sys.executable, "-m", "x_reader.mcp_server"],
        help="Stdio server command; put this option last (supports ssh)",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_commit):
        parser.error("--expected-commit must be a full lowercase Git commit SHA")
    if not re.fullmatch(r"[0-9]{1,20}", args.post_id) or int(args.post_id) <= 2**53 - 1:
        parser.error("--post-id must be a decimal string above 2^53-1, at most 20 digits")
    if not args.command:
        parser.error("--command requires an executable")
    try:
        report = asyncio.run(_run(args.command, args.expected_commit, args.post_id))
    except VerificationError as exc:
        parser.exit(1, f"Verification failed: {exc}\n")
    except Exception as exc:  # noqa: BLE001 -- sanitize arbitrary transport failures at the CLI boundary
        # Transport errors can contain commands or runtime details. Keep output bounded.
        parser.exit(1, f"Verification failed ({type(exc).__name__}). Check server diagnostics.\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
