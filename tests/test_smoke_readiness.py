from __future__ import annotations

import importlib
import json
import os
import sys
from importlib.metadata import version
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_console_script_serves_tools_outside_repo_cwd(tmp_path: Path, capfd):
    script = Path(sys.executable).with_name("x-reader-mcp.exe" if os.name == "nt" else "x-reader-mcp")
    assert script.exists(), f"missing console script: {script}"

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["X_READER_DB_PATH"] = str(tmp_path / "accounts.db")
    server = StdioServerParameters(command=str(script), cwd=tmp_path, env=env)

    stderr_path = tmp_path / "stderr.log"
    with anyio.fail_after(30), stderr_path.open("w") as stderr:
        async with stdio_client(server, errlog=stderr) as streams, ClientSession(*streams) as client:
            initialized = await client.initialize()
            tools = (await client.list_tools()).tools
            invalid = await client.call_tool("search_x", {})
            unavailable = await client.call_tool("search_x", {"query": "topic"})

    assert {tool.name for tool in tools} == {
        "search_x", "get_x_user_posts", "get_x_post", "get_x_thread",
        "read_x_user", "read_x_post",
    }
    assert invalid.is_error is True
    assert unavailable.is_error is True
    assert unavailable.structured_content["error"]["code"] == "ACCOUNT_UNAVAILABLE"
    assert unavailable.structured_content["error"]["retryable"] is False
    assert initialized.server_info.version.startswith(version("x-reader") + "+git.")
    captured = capfd.readouterr()
    assert captured.out == ""
    diagnostics = [
        json.loads(line) for line in stderr_path.read_text().splitlines()
        if '"event": "x_reader_request"' in line
    ]
    assert len(diagnostics) == 2
    assert diagnostics[0]["tool"] == "search_x"
    assert diagnostics[0]["outcome"] == "validation_error"
    assert diagnostics[1]["outcome"] == "account_unavailable"


def test_reader_uses_configured_absolute_db_path(monkeypatch, tmp_path: Path):
    reader_module = importlib.import_module("x_reader.reader")
    captured: dict[str, str] = {}

    class FakeApi:
        def __init__(self, db_path: str, **kwargs):
            captured["db_path"] = db_path
            assert kwargs == {
                "raise_when_no_account": True, "wait_timeout": 5, "wait_interval": 0.5,
            }

    db_path = tmp_path / "state" / "accounts.db"
    monkeypatch.setenv("X_READER_DB_PATH", str(db_path))
    monkeypatch.setattr(reader_module, "API", FakeApi)

    reader_module.TwscrapeReader()

    assert captured["db_path"] == str(db_path.resolve())
