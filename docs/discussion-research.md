# Discussion research: retrieval contract and upstream findings

## Scope

The existing six tools collect evidence. The skill at
`plugin/skills/discussion-research/SKILL.md` guides sample design, source inspection,
claim grouping, sentiment interpretation, and reporting. No classifier, extra LLM,
background worker, or new MCP tool is required.

The skill is maintained here as the source for the app-backed plugin package.
Publishing it preserves the existing plugin identity, app binding, and presentation;
the skill also includes a fallback for older discovered tool schemas.

## Search controls and sampling

`search_x` retains its default response and adds optional controls:

| Argument | Behavior |
| --- | --- |
| `ranking="recent"` | Default: X Latest product, then local newest-first ordering. |
| `ranking="top"` | X Top product, preserving its order after filtering and deduplication. |
| `since`, `until` | Timezone-aware boundaries: inclusive start, exclusive end; local filters over the fetched sample. |
| `include_replies`, `include_reposts` | Both default true for search; explicit local exclusions when false. |
| `required_terms` | All phrases must occur as case-insensitive substrings of the post's own text. No quote, URL-content, or semantic matching. |
| `include_metrics` | Adds counters to minimal/compact posts without media, links, or mentions. Also available on `read_x_user` and `read_x_post`, including context posts. |
| `include_sampling` | Adds a search receipt with retrieval time, actual query, criteria, counts, exclusion IDs/reasons, and coverage limitations. Also available on `read_x_post` for context selection counts and retrieval times. |

Date filters do not add upstream search operators. This avoids promising historical
coverage or rewriting a user's query using unverified X syntax. To target a historical
window upstream, callers can supply their own X query operators and inspect returned
timestamps. No semantic/exact matching mode or arbitrary relevance score is advertised.

Each call makes one bounded upstream search. Overfetching retains its existing 40–200
target range and the tool's public result limit remains 50. Twscrape's limit is a target,
so `fetched_count` reports the actual number received, not the requested number.

Receipt counts satisfy `fetched_count = excluded_count + duplicate_count + eligible_count`.
Exclusions record the first applicable deterministic reason. Deduplication keeps the first
eligible occurrence of an ID; absent IDs retain the existing behavior. `omitted_by_limit`
counts eligible fetched posts that did not fit the returned limit. It says nothing about
unfetched posts. `total_matching` and `has_more` are null because the parsed twscrape API
does not establish completeness or provide a reusable continuation cursor here.

`retrieved_at` is the UTC time the upstream fetch completed, not an individual metric's
measurement time. Results are a bounded upstream sample and are not representative of
all X discussion. Reply-context selection has the same coverage caveat.

## Post and context receipts

With `read_x_post(include_sampling=true)`, the receipt describes the selected context;
the anchor remains in the separate `post` field. `anchor_retrieved_at` and `retrieved_at`
record fetch completion times. They are not exact metric measurement timestamps or an
atomic snapshot across all posts. The default response remains unchanged when this
option is false. No extra upstream requests are made to produce a receipt.

Context counts obey:

```text
fetched_count + anchor_injected_count
  = filtered_out_count + duplicate_count + anchor_excluded_count + eligible_count
eligible_count = returned_count + omitted_by_limit
```

`anchor_injected_count` records restoring a fetched anchor absent from the conversation
sample; `anchor_excluded_count` records removing it from context. Replies must be direct
replies, author threads must match the anchor author and conversation, and full
conversation samples must match the conversation. Context is ordered oldest first within
the fetched sample before applying the requested return limit. Parent context uses one
direct lookup; `context="none"` makes no context requests. Both retain unknown conversation
completeness rather than implying that the broader discussion was fully retrieved.

## Links

Full post and quote/repost previews remove identical normalized URL/text pairs, preserving
first occurrence and order. Different labels and query parameters are retained. URLs
are not canonicalized, tracking parameters are not stripped, and source objects are not
mutated. This covers the duplicate expanded-link case in the user diagnostic without
introducing URL interpretation rules.

## Execution failures

Operational errors use native MCP execution-error results (`isError=true`) with an
`error` object in `structuredContent` and an identical JSON copy in text content:

```json
{
  "error": {
    "code": "ENDPOINT_BUSY",
    "category": "endpoint_busy",
    "message": "X accounts are temporarily locked for this endpoint. Retry after the indicated delay.",
    "retryable": true,
    "retry_after_seconds": 120,
    "endpoint": "SearchTimeline"
  }
}
```

Endpoint state is read through twscrape's account pool only after acquisition fails.
No cookies, account names, proxies, or raw error messages enter the error object.
Locks are never cleared and accounts are never refreshed automatically. The retry delay
is the earliest observed queue-lock expiry, rounded up, not a guarantee of later success.
An inactive/empty pool is non-retryable pending operator action; uncertain availability
after a race is retryable with no invented delay. Endpoint locks do not distinguish
in-use locks from upstream rate-limit locks. They must not be labeled expired credentials.

Input-validation errors remain validation errors. Known domain failures retain their
not-found distinction; the legacy missing-thread response remains an empty posts array.
Clients must inspect the execution-error payload: a platform may still label an MCP
`isError` response `INVALID_ARGUMENT`. x-reader cannot control that outer host label,
and does not misuse JSON-RPC protocol-error codes for ordinary tool execution failures.

## Investigation on 2026-10-27

Read-only VPS inspection found one active account. The journal recorded eight failed
searches and eight successful searches in the inspected two-hour window; direct reads
also succeeded. Failed searches between 07:10 and 07:14 UTC reported the SearchTimeline
queue unavailable until 07:17:32. At the later inspection the lock had expired. This
confirms a queue lock during those failures, without proving whether rate limiting or
in-flight work originally created it. No account or production configuration was changed.

Related upstream evidence checked:

- [Issue #351](https://github.com/vladkens/twscrape/issues/351) reports SearchTimeline
  rate-limit responses failing to rotate accounts. Its multi-account scenario is relevant
  context, not proof of the cause on our single-account deployment.
- [PR #317](https://github.com/vladkens/twscrape/pull/317), merged, introduced the bounded
  account wait already used here. It provides the short contention retry without an
  additional application retry loop.
- [PR #347](https://github.com/vladkens/twscrape/pull/347), open when checked, addresses
  failed requests being returned as empty/missing results.
- [PR #364](https://github.com/vladkens/twscrape/pull/364), open when checked, proposes
  rate-limit rotation and explicit single-object parsing failures for the next release.
- [PR #362](https://github.com/vladkens/twscrape/pull/362), merged on upstream main,
  refreshes operations/mocks and documents a curl backend workaround for a specific
  user-by-ID Cloudflare failure. That is a different endpoint and not a reason to change
  our backend automatically.

[The latest published release](https://github.com/vladkens/twscrape/releases/latest)
was still 0.20.1. Keep the released pin; do not vendor an unreleased queue client or
upgrade to a moving branch. Reconsider when a released version includes the explicit
failure/rotation fixes and passes our adapter/normalization and live-read checks.

The current dependency can still suppress some upstream failures internally. A sampling
receipt cannot turn an apparently empty upstream result into proof of no discussion.
Genuine cursor pagination or a dedicated collection tool needs a separately verified
upstream contract and evidence that the skill's bounded procedure is stable in daily use.
