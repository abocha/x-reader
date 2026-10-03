# Security policy

## Supported version

This is a small personal project under active development. Security fixes are applied to the current `main` branch; older commits and tags are not maintained as separate supported release lines.

## Reporting a vulnerability

Please do not open a public issue containing credentials, session material, private tunnel identifiers, or a working exploit against a deployed instance.

Prefer GitHub's private vulnerability reporting for this repository when it is available. Otherwise, contact the repository owner through the GitHub profile and share only the minimum information needed to establish a private reporting channel.

Useful reports include:

- the affected component or file;
- reproduction steps;
- the security impact;
- whether the issue requires a live X/twscrape account, HTTP exposure, or MCP/tunnel access;
- any suggested mitigation, if known.

## Security boundaries

`x-reader` is designed as a read-only service, but it still handles sensitive runtime material.

- `accounts.db` may contain X/twscrape authentication state. It must remain outside version control and should be readable only by the service account that needs it.
- Secure MCP Tunnel runtime keys belong in environment variables or protected service environment files, not source code, shell history, logs, screenshots, or issue bodies.
- The FastAPI adapter is a compatibility/development surface. The supported production deployment does not expose it as a public ingress.
- In-process rate limiting is a safety control, not an authentication mechanism.
- The project does not intentionally bypass X access controls and should only be used with accounts and content the operator is authorized to access.

Operational secret-handling guidance is documented in [docs/secure-mcp-tunnel-runbook.md](docs/secure-mcp-tunnel-runbook.md).
