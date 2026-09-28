# AGENTS.md

## Repository expectations

This repository is a small read-only X/Twitter reader with shared domain logic exposed through MCP and HTTP adapters.

Prefer the smallest change that satisfies the requested behavior. Preserve existing public contracts unless the task explicitly changes them.

## Architecture

Keep responsibilities separated:

* `reader.py` owns twscrape/upstream access.
* `service.py` owns filtering, classification, ordering, deduplication, and use-case behavior.
* `normalize.py` owns stable public representations.
* `mcp_server.py` is an MCP adapter.
* `app.py` is an HTTP adapter.

Avoid duplicating domain behavior across adapters or adding upstream calls merely to reshape an existing result.

Use existing abstractions when they fit. Do not introduce new layers, helpers, or configuration mechanisms without a concrete need.

## Compatibility

Treat existing HTTP `/v1/...` behavior and legacy MCP tools as compatibility surfaces.

When changing richer MCP behavior or normalized representations, verify whether existing callers should remain unchanged.

Preserve:

* stable string post/user IDs in normalized output;
* existing ordering and filtering semantics;
* timeline provenance;
* pinned-post behavior;
* bounded result limits;
* read-only behavior.

Do not silently reinterpret upstream metadata such as X language classification.

## Working style

Infer routine implementation details from the task and repository context and continue until the requested outcome is complete.

Do not stop after producing a plan when implementation is requested.

Read only the documentation and code relevant to the current change. Do not preload the entire repository or a stack of design documents for small tasks.

For substantial implementation, refactoring, or architectural work, use the local complexity-discipline guidance when available:

`D:/code/codex-workflow/skills/complexity-discipline/SKILL.md`

User/task instructions take precedence over guidance in that skill.

If skill guidance would cause you to stop, request unnecessary approval, or materially diverge from the requested task, identify the exact instruction before doing so.

## Testing and static checks

Use `uv` for the project environment and commands.

Run focused tests and checks while developing when they help isolate a change.

For substantive code changes, complete the repository's standard validation before considering the implementation finished:

```bash
uv run pytest
uv run ruff check .
uv run ty check .
```

The test suite uses local fixtures and does not require production access. Run relevant tests, fix failures caused by the requested change, and rerun affected checks without asking for approval at each step.

Treat Ruff and ty as normal project tooling. Fix lint or type-check failures caused by the requested change.

Do not broaden the task into unrelated cleanup merely to make pre-existing warnings or failures disappear. If a standard check fails for a clearly pre-existing, unrelated reason, identify that separately in the final report.

Do not add tests that merely mirror implementation details. Prefer tests for observable behavior, compatibility boundaries, regressions, and request-count/performance invariants when relevant.

Once the required checks pass, do not repeat or broaden validation unless new changes, failures, or unresolved concerns justify it.

## Scope discipline

Do not fold unrelated cleanup into a requested change.

If you discover an unrelated issue, report it separately or create/follow a dedicated issue when the task authorizes that workflow.

In particular, deployment and shared VPS ingress are separate concerns. Do not modify Caddy, tunnel-client, VPS configuration, or deployment topology unless the task explicitly concerns them.

## Git and delivery

Inspect the current branch and worktree before making changes.

Follow the delivery workflow requested by the task. Do not assume every change should go directly to `main`, and do not merge or deploy unless explicitly authorized.

Before committing or opening a PR, inspect the final diff for:

* unnecessary complexity;
* accidental public-contract changes;
* duplicated logic;
* unrelated edits;
* generated or temporary files.

When reporting completed work, focus on reviewable evidence: what changed, tests/checks run, commit or PR references when applicable, and any remaining concern that materially affects review.

## Code Review Rules

Flag changes that:

* move domain behavior into MCP or HTTP adapters instead of the shared service;
* duplicate upstream X requests when existing fetched data is sufficient;
* change compatibility surfaces without an explicit requirement;
* expand scope into unrelated deployment or infrastructure work;
* add abstractions whose only purpose is to support a single simple call site.

Prefer the simpler implementation when two approaches provide the same observable behavior and compatibility.
