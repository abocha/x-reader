import json
import subprocess
import sys
from importlib.metadata import version
from types import SimpleNamespace

import pytest
from mcp import Client

import x_reader.mcp_server as server_module
from x_reader.verify import VerificationError, verify_deployment

pytestmark = pytest.mark.anyio
COMMIT = "a" * 40
POST_ID = "2096055605538799675"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(server_module, "_server_version", lambda: f"0.1.0+git.{COMMIT}")

    class Reader:
        def __init__(self):
            self.calls = []

        async def tweet(self, post_id):
            self.calls.append(post_id)
            return {"id": post_id}

    reader = Reader()
    return server_module.create_mcp_server(reader), reader


async def test_verifier_checks_real_tool_schemas_and_exact_large_id(server):
    mcp, reader = server
    async with Client(mcp) as client:
        report = await verify_deployment(client, COMMIT, POST_ID)
    assert report["status"] == "ok"
    assert report["commit"] == COMMIT
    assert report["verified_post_id"] == POST_ID
    assert len(report["tools"]) == 6
    assert reader.calls == [int(POST_ID)]


@pytest.mark.parametrize("reported", ["0.1.0", f"0.1.0+git.{COMMIT}.dirty", "0.1.0+git." + "b" * 40])
async def test_verifier_refuses_unknown_dirty_or_wrong_revision_before_upstream_calls(server, monkeypatch, reported):
    mcp, reader = server
    async with Client(mcp) as client:
        monkeypatch.setattr(type(client), "server_info", property(lambda self: SimpleNamespace(name="x-reader", version=reported)))
        with pytest.raises(VerificationError, match="revision"):
            await verify_deployment(client, COMMIT, POST_ID)
    assert reader.calls == []


@pytest.mark.parametrize("tool,parameter", [("get_x_post", "tweet_id"), ("get_x_thread", "tweet_id"), ("read_x_post", "post")])
async def test_verifier_refuses_numeric_plugin_schemas_before_upstream_calls(server, monkeypatch, tool, parameter):
    mcp, reader = server
    async with Client(mcp) as client:
        listing = await client.list_tools()
        next(item for item in listing.tools if item.name == tool).input_schema["properties"][parameter] = {"type": "integer"}

        async def list_tools():
            return listing

        monkeypatch.setattr(client, "list_tools", list_tools)
        with pytest.raises(VerificationError, match="string"):
            await verify_deployment(client, COMMIT, POST_ID)
    assert reader.calls == []


@pytest.mark.parametrize("returned_id,is_error", [(int(POST_ID), False), ("2096055605538799600", False), (None, True)])
async def test_verifier_refuses_failed_or_imprecise_large_id_responses(server, monkeypatch, returned_id, is_error):
    mcp, _ = server
    async with Client(mcp) as client:
        async def call_tool(name, arguments):
            assert name == "get_x_post"
            assert arguments == {"tweet_id": POST_ID}
            return SimpleNamespace(is_error=is_error, structured_content={"post": {"id": returned_id}})

        monkeypatch.setattr(client, "call_tool", call_tool)
        with pytest.raises(VerificationError, match="post|ID"):
            await verify_deployment(client, COMMIT, POST_ID)


@pytest.mark.parametrize("problem", ["missing_tool", "not_read_only"])
async def test_verifier_rejects_changed_tool_surface_before_upstream_calls(server, monkeypatch, problem):
    mcp, reader = server
    async with Client(mcp) as client:
        listing = await client.list_tools()
        if problem == "missing_tool":
            listing.tools.pop()
        else:
            listing.tools[0].annotations = None

        async def list_tools():
            return listing

        monkeypatch.setattr(client, "list_tools", list_tools)
        with pytest.raises(VerificationError, match="six|read-only"):
            await verify_deployment(client, COMMIT, POST_ID)
    assert reader.calls == []


def test_verification_cli_runs_against_a_real_stdio_process(tmp_path):
    server_script = tmp_path / "server.py"
    server_script.write_text(f'''
import x_reader.mcp_server as server_module

class Reader:
    async def tweet(self, post_id):
        return {{"id": post_id}}

server_module._server_version = lambda: "0.1.0+git.{COMMIT}"
server_module.create_mcp_server(Reader()).run()
''')
    result = subprocess.run(
        [sys.executable, "-m", "x_reader.verify", "--expected-commit", COMMIT,
         "--post-id", POST_ID, "--command", sys.executable, str(server_script)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["commit"] == COMMIT
    assert report["verified_post_id"] == POST_ID
    assert report["status"] == "ok"


def test_runtime_revision_tracks_real_checkout_and_dirty_sources(tmp_path, monkeypatch):
    source = tmp_path / "src" / "x_reader" / "mcp_server.py"
    source.parent.mkdir(parents=True)
    source.write_text("# source\n")
    (tmp_path / "pyproject.toml").write_text("# project\n")
    for args in (
        ["init", "-q"], ["add", "."],
        ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True,
    ).stdout.strip()
    monkeypatch.setattr(server_module, "__file__", str(source))
    assert server_module._server_version() == f"{version("x-reader")}+git.{commit}"
    source.write_text("# changed source\n")
    assert server_module._server_version() == f"{version("x-reader")}+git.{commit}.dirty"
