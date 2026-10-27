# x-reader

[![tests](https://github.com/abocha/x-reader/actions/workflows/test.yml/badge.svg)](https://github.com/abocha/x-reader/actions/workflows/test.yml)

A small read-only X/Twitter reader built for tool-using LLM clients built on top of [twscrape](https://github.com/vladkens/twscrape)

`x-reader` keeps upstream access, domain behavior, normalization, and its MCP adapter separate. The x-reader plugin uses the service over stdio MCP through a private Secure MCP Tunnel.

## What it does

- searches current public X/Twitter posts by text, author, or both;
- reads recent user timelines with optional replies, reposts, and account details;
- reads a single post with optional parent, author-thread, reply, or conversation context;
- normalizes unstable upstream objects into a smaller, predictable public shape;
- preserves large X post IDs as strings at MCP boundaries to avoid JavaScript precision loss;
- offers `minimal`, `compact`, and `full` post projections so LLM callers can trade metadata for payload size without causing extra upstream requests;
- keeps all MCP tools read-only and rate-limited.

This is an independent project and is not affiliated with X Corp.

## Architecture

```mermaid
flowchart LR
    ChatGPT["MCP / agent client"] --> Tunnel["Secure MCP Tunnel"]
    Tunnel --> MCP["MCP adapter"]

    MCP --> Service["XReaderService"]

    Service --> Reader["TwscrapeReader"]
    Reader --> DB[("accounts.db")]
    Reader --> X["X / Twitter"]

    Service --> Normalize["normalization + detail projection"]
    Normalize --> MCP
```

The core design rule is simple: adapters translate requests, while `XReaderService` owns filtering, ordering, deduplication, timeline semantics, and context behavior. Upstream access stays in `reader.py`; stable output shapes stay in `normalize.py`.

The service owns behavior shared by all six MCP tools; the adapter owns tool schemas and transport error handling.

## MCP surface

The current server exposes six read-only tools:

| Tool | Purpose |
| --- | --- |
| `search_x` | Search posts by query and/or author filters. |
| `read_x_user` | Read a user profile and recent timeline with optional replies, reposts, and account details. |
| `read_x_post` | Read one post plus optional parent/thread/replies/conversation context. |
| `get_x_user_posts` | Compatibility tool for recent original posts from one user. |
| `get_x_post` | Compatibility tool for one post by decimal string ID. |
| `get_x_thread` | Compatibility tool for an author's thread around a post. |

The richer tools accept three post detail levels:

| Detail | Intended use | Shape |
| --- | --- | --- |
| `minimal` | broad discovery / larger result sets | core identity, text, author handle, and only context fields that add information |
| `compact` | structured exploration | stable IDs, author identity, reply/repost/quote state, conversation provenance |
| `full` | focused drill-down | compact fields plus metrics, media, links, mentions, hashtags, sensitivity, and cards |

`search_x` and `read_x_user` default to `minimal`; `read_x_post` defaults to `full`. The older compatibility tools preserve their existing full response shape.

For discussion research, `search_x` supports explicit recent/Top selection, local date
and text filters, lightweight metrics, and an opt-in sampling receipt. The
[discussion-research skill](plugin/skills/discussion-research/SKILL.md) guides evidence
collection and interpretation. See [the retrieval contract and upstream findings](docs/discussion-research.md)
for sampling limits, error codes, and the boundary between retrieval and analysis.

## Quick start

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- a twscrape-compatible `accounts.db`

Credential/account provisioning is intentionally outside this repository. The account database may contain sensitive authentication material and is gitignored.

Install the locked environment:

```bash
uv sync --frozen
```

Point x-reader at the account database:

```bash
export X_READER_DB_PATH=/absolute/path/to/accounts.db
```

Start the MCP server over stdio:

```bash
uv run x-reader-mcp
```

Upstream operations have a 20-second timeout and a five-second account wait. Tool errors
distinguish missing posts from account unavailability and timeouts. Each executed tool
logs its duration, result count, and outcome to stderr without including request inputs.
Operational failures include structured codes and retry guidance. Endpoint exhaustion
does not mean the query is invalid or the topic has no discussion.

## Development

The repository uses `uv` for dependency management and runs three checks in CI on pull requests and pushes to `main`:

```bash
uv run pytest
uv run ruff check .
uv run ty check .
```

The test suite is fixture-driven and does not require live X access.

### Repository layout

```text
src/x_reader/
  reader.py       # twscrape/upstream access
  service.py      # use-case behavior and timeline semantics
  normalize.py    # stable public representations and detail projections
  mcp_server.py   # MCP adapter and tool schemas
  verify.py       # read-only deployment/schema/large-ID verification command
  locators.py     # user/post locator parsing and validation
  filters.py      # shared filtering, ordering, and classification helpers
  rate_limit.py   # in-process sliding-window limiter

tests/            # behavior, compatibility, regression, and smoke-readiness tests
docs/             # deployment/runbook documentation
```

## Deployment

The supported production path is:

```text
ChatGPT / MCP client
  -> OpenAI Secure MCP Tunnel
  -> tunnel-client
  -> x-reader-mcp over stdio
  -> TwscrapeReader
  -> X/Twitter
```

The unused HTTP adapter has been removed; the supported entrypoint is stdio MCP. See [the Secure MCP Tunnel runbook](docs/secure-mcp-tunnel-runbook.md) for the deployment and operational details.

`uv run x-reader-verify --expected-commit FULL_SHA --post-id LARGE_PUBLIC_POST_ID`
checks the server's clean Git revision, six read-only tools, string-ID schemas, and one
live post response. The runbook covers remote stdio commands and the separate plugin
discovery check. This verification command requires live X access; the test suite does not.
Use `--research-query 'YOUR PUBLIC TOPIC'` for the additional sampling/metrics acceptance checks.

## Engineering notes

A few constraints shaped the implementation:

- **Stable IDs at tool boundaries.** X post IDs exceed JavaScript's safe integer range, so MCP schemas require decimal strings where precision matters.
- **One behavioral core.** All MCP tools reuse the same service instead of duplicating filtering or context logic.
- **Projection without refetching.** `minimal`, `compact`, and `full` are output projections over the same fetched records, not different retrieval paths.
- **Compatibility is explicit.** Older MCP tools are kept as compatibility surfaces while richer read tools evolve.
- **Private production ingress.** The service runs behind a secure tunnel and stdio MCP boundary.

## Security

Secrets, session databases, and runtime keys do not belong in the repository. `accounts.db` and `.env` are ignored by Git.

For vulnerability reporting and the project's security assumptions, see [SECURITY.md](SECURITY.md).
