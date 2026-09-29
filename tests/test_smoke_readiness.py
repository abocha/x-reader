from __future__ import annotations

import importlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.types import TextContent


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_project_imports_outside_repo_cwd(tmp_path: Path):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import x_reader"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_mcp_console_script_starts_outside_repo_cwd(tmp_path: Path):
    script = Path(sys.executable).with_name("x-reader-mcp.exe" if os.name == "nt" else "x-reader-mcp")
    assert script.exists(), f"missing console script: {script}"

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["X_READER_DB_PATH"] = str(tmp_path / "accounts.db")

    process = subprocess.Popen(
        [str(script)],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stderr is not None
        time.sleep(0.5)
        assert process.poll() is None, process.stderr.read()
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_reader_uses_configured_absolute_db_path(monkeypatch, tmp_path: Path):
    reader_module = importlib.import_module("x_reader.reader")
    captured: dict[str, str] = {}

    class FakeApi:
        def __init__(self, db_path: str):
            captured["db_path"] = db_path

    db_path = tmp_path / "state" / "accounts.db"
    monkeypatch.setenv("X_READER_DB_PATH", str(db_path))
    monkeypatch.setattr(reader_module, "API", FakeApi)

    reader_module.TwscrapeReader()

    assert captured["db_path"] == str(db_path.resolve())


def test_thread_filter_anchors_on_requested_tweet_id():
    thread_module = importlib.import_module("x_reader.thread")

    items = [
        {
            "id": 999,
            "date": "2026-09-05T00:00:00Z",
            "conversationId": 100,
            "user": {"username": "someone_else"},
        },
        {
            "id": 101,
            "date": "2026-09-05T00:01:00Z",
            "conversationId": 100,
            "user": {"username": "OpenAI"},
        },
        {
            "id": 102,
            "date": "2026-09-05T00:02:00Z",
            "conversationId": 100,
            "user": {"username": "OpenAI"},
        },
    ]

    filtered = thread_module.filter_author_thread(items, anchor_tweet_id=101)

    assert [item["id"] for item in filtered] == [101, 102]


def test_rest_thread_returns_empty_list_when_anchor_does_not_exist():
    app_module = importlib.import_module("x_reader.app")

    class FakeReader:
        async def tweet(self, tweet_id: int):
            return None

    client = TestClient(
        app_module.create_app(FakeReader()),
        raise_server_exceptions=False,
    )

    response = client.get("/v1/tweets/999/thread")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_mcp_enforces_its_own_request_budget():
    mcp_module = importlib.import_module("x_reader.mcp_server")

    class FakeReader:
        def __init__(self) -> None:
            self.calls = 0

        async def tweet(self, tweet_id: int) -> dict:
            self.calls += 1
            return {
                "id": tweet_id,
                "url": f"https://x.com/OpenAI/status/{tweet_id}",
                "date": "2026-09-05T00:00:00Z",
                "rawContent": "Test",
                "user": {"username": "OpenAI", "displayname": "OpenAI"},
                "replyCount": 0,
                "retweetCount": 0,
                "likeCount": 0,
                "quoteCount": 0,
                "bookmarkedCount": 0,
                "viewCount": 0,
                "conversationId": tweet_id,
                "inReplyToTweetId": None,
                "links": [],
                "media": {"photos": [], "videos": [], "animated": []},
            }

    reader = FakeReader()
    server = mcp_module.create_mcp_server(
        reader,
        rate_limit=1,
        rate_window_seconds=3600,
    )

    async with Client(server) as client:
        first = await client.call_tool("get_x_post", {"tweet_id": "1"})
        second = await client.call_tool("get_x_post", {"tweet_id": "2"})

    assert first.is_error is False
    assert second.is_error is True
    assert isinstance(second.content[0], TextContent)
    assert "rate limit" in second.content[0].text.lower()
    assert reader.calls == 1
