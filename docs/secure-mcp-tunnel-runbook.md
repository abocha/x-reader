# Secure MCP Tunnel runbook for x-reader

Status: working end to end in ChatGPT web as of 2026-09-05.

## Goal

Make the private `x-reader` MCP server callable naturally from ChatGPT without exposing the MCP server to the public internet.

Working path:

```text
ChatGPT web
  -> custom developer-mode plugin/app
  -> OpenAI Secure MCP Tunnel
  -> tunnel-client on VPS
  -> x-reader stdio MCP
  -> TwscrapeReader
  -> X/Twitter
```

Confirmed live behavior: ChatGPT successfully called `Search X` through the plugin and received normalized post arrays.

The supported production path is the Secure MCP Tunnel to `x-reader-mcp` over stdio. Production
`x-reader` has no Caddy or public HTTP dependency. The FastAPI `/v1/...` adapter remains an
application compatibility surface, but it is not part of the current production deployment. The
former port-8789/Caddy ingress was retired as legacy infrastructure on 2026-09-29.

## x-reader MCP surface

The MCP server exposes four read-only tools:

- `search_x`
- `get_x_user_posts`
- `get_x_post`
- `get_x_thread`

The project is installable as a normal `src/` layout package and exposes the console entrypoint:

```bash
x-reader-mcp
```

`TwscrapeReader` uses a cwd-independent DB path, with an explicit override:

```bash
X_READER_DB_PATH=/home/ubuntu/x-reader/accounts.db
```

The MCP adapter has its own in-process request budget of 60 calls/hour. REST keeps its existing limiter separately.

## VPS prerequisites

Expected host layout:

```text
/home/ubuntu/x-reader
/home/ubuntu/x-reader/accounts.db
/home/ubuntu/x-reader/.venv/bin/x-reader-mcp
```

Update and verify the app:

```bash
cd ~/x-reader
git pull --ff-only
uv sync --frozen
uv run pytest -q
```

Known-good test state after MCP cleanup:

```text
44 passed, 1 existing Starlette deprecation warning
```

Local stdio smoke test:

```bash
X_READER_DB_PATH=/home/ubuntu/x-reader/accounts.db \
  uv run x-reader-mcp
```

Expected behavior: process waits silently for MCP input. Stop with Ctrl-C.

## tunnel-client installation

Known-good version:

```text
v0.0.14
```

On Linux x86_64, install the full client release artifact, not the narrower runtime-only variants.

```bash
set -euo pipefail

RELEASE=v0.0.14
PLATFORM=linux-amd64
STEM="tunnel-client-${RELEASE}-${PLATFORM}"
BASE="https://github.com/openai/tunnel-client/releases/download/${RELEASE}"

tmp="$(mktemp -d)"
cd "$tmp"

curl -fLO "${BASE}/${STEM}.zip"
curl -fLO "${BASE}/SHA256SUMS.txt"
grep " ${STEM}.zip$" SHA256SUMS.txt | sha256sum -c -
unzip -q "${STEM}.zip" -d extracted

BIN="$(find extracted -type f -name tunnel-client -print -quit)"
test -n "$BIN"
sudo install -m 0755 "$BIN" /usr/local/bin/tunnel-client

cd /
rm -rf "$tmp"

tunnel-client --version
```

Known-good output begins with:

```text
0.0.14
```

## Secrets and identifiers

Do not commit or paste runtime secrets into chat/logs.

Required values:

- tunnel ID from Platform Tunnels management
- runtime API key from Platform Runtime API keys

The runtime API key principal needs Tunnels `Read` + `Use`.

For an interactive shell, avoid storing the key in shell history:

```bash
read -rsp 'Runtime API key: ' CONTROL_PLANE_API_KEY
export CONTROL_PLANE_API_KEY
echo

read -rp 'Tunnel ID: ' CONTROL_PLANE_TUNNEL_ID
export CONTROL_PLANE_TUNNEL_ID

export X_READER_DB_PATH=/home/ubuntu/x-reader/accounts.db
```

Sanity check without printing the secret:

```bash
printf 'Tunnel ID: %s\nRuntime key: %s\nDB: %s\n' \
  "$CONTROL_PLANE_TUNNEL_ID" \
  "${CONTROL_PLANE_API_KEY:+SET}" \
  "$X_READER_DB_PATH"
```

## Create the tunnel profile

Use the stdio sample and the installed x-reader console entrypoint:

```bash
tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile x-reader \
  --tunnel-id "$CONTROL_PLANE_TUNNEL_ID" \
  --mcp-command "/home/ubuntu/x-reader/.venv/bin/x-reader-mcp"
```

Expected profile location:

```text
/home/ubuntu/.config/tunnel-client/x-reader.yaml
```

The generated profile references the runtime key from `env:CONTROL_PLANE_API_KEY`; the secret should not be embedded into the YAML.

## Health listener conflict

On this VPS, `127.0.0.1:8080` was already occupied. The x-reader tunnel was therefore run on `8081`.

Doctor:

```bash
tunnel-client doctor \
  --profile x-reader \
  --health.listen-addr 127.0.0.1:8081 \
  --explain
```

Run:

```bash
tunnel-client run \
  --profile x-reader \
  --health.listen-addr 127.0.0.1:8081
```

Keep this process running while creating the ChatGPT plugin and during every MCP call unless systemd supervision is configured as documented below.

Useful local checks from a second SSH session:

```bash
curl -i http://127.0.0.1:8081/healthz
curl -i http://127.0.0.1:8081/readyz
curl -s http://127.0.0.1:8081/metrics | grep -E 'commands_poll|control_plane'
```

The operator UI is available locally at:

```text
http://127.0.0.1:8081/ui
```

Use SSH port forwarding if viewing it from a workstation.

## What successful startup looks like

Observed healthy startup included:

```text
[controlplane] poller started
[adminui] WEB UI: http://127.0.0.1:8081/ui
[controlplane] tunnel metadata fetched
tunnel-client started
```

During ChatGPT plugin discovery, the dispatcher then logged commands being forwarded to the MCP server.

That is strong evidence that the chain reached the local stdio MCP process.

## ChatGPT plugin setup

In ChatGPT web:

1. Developer mode must be enabled.
2. Create a new developer-mode plugin/app.
3. Choose `Tunnel` as the connection type.
4. Select the same tunnel used by the running `tunnel-client` profile.
5. Use no MCP-side authentication for this private stdio x-reader setup.
6. Complete the risk acknowledgement and create the plugin while the daemon is running.

This was confirmed working on a personal ChatGPT Plus account in the web UI on 2026-09-05, despite public plan documentation being ambiguous/incomplete around Plus developer MCP availability.

## Important failure mode: HTTP 424 during plugin creation

Observed ChatGPT response:

```json
{
  "detail": {
    "type": "mcp_error",
    "developer_message": "MCP SSE probe returned 404 from openai.org",
    "kind": "invalid_response",
    "upstream_status": 404
  }
}
```

This matched `openai/tunnel-client` issue #35.

Do not immediately assume this means the ChatGPT plan is unsupported. The same symptom has been reproduced on other plans when the tunnel runtime was not actually polling the OpenAI Control Plane successfully.

Before debugging the MCP server itself, verify:

- `tunnel-client run` is currently running
- `/readyz` returns 200
- Control Plane polling has completed successfully
- the selected ChatGPT tunnel matches the profile tunnel
- the runtime key has Tunnels `Read` + `Use`

A tunnel merely existing in Platform or appearing in the ChatGPT picker is not enough.

## Conversation-level quirk

A plugin connected after a conversation has already started may not be usable in that older conversation. A fresh chat with the developer plugin enabled successfully called x-reader after an older thread rejected developer MCP use.

If a working plugin reports that the current conversation does not support developer MCPs, start a new chat instead of debugging the VPS.

## Confirmed end-to-end success

In a fresh ChatGPT web conversation, the x-reader plugin successfully executed `Search X` with natural-language user intent and returned post arrays. This confirms:

```text
ChatGPT -> custom plugin -> Secure MCP Tunnel -> tunnel-client -> x-reader MCP -> X
```

## Long-lived systemd service

Do not keep an SSH terminal open permanently. Run `tunnel-client` as a systemd service so it survives logout, restarts on failure, and starts again after VPS reboot.

First stop any foreground `tunnel-client run ...` process with Ctrl-C so it releases `127.0.0.1:8081`.

Store the runtime API key in a root-readable EnvironmentFile rather than in the unit or shell history:

```bash
sudo install -d -m 0755 /etc/x-reader-tunnel

read -rsp 'Runtime API key: ' CONTROL_PLANE_API_KEY
echo

printf 'CONTROL_PLANE_API_KEY=%s\nX_READER_DB_PATH=%s\n' \
  "$CONTROL_PLANE_API_KEY" \
  "/home/ubuntu/x-reader/accounts.db" \
  | sudo tee /etc/x-reader-tunnel/env >/dev/null

unset CONTROL_PLANE_API_KEY
sudo chown root:root /etc/x-reader-tunnel/env
sudo chmod 600 /etc/x-reader-tunnel/env
```

Verify the file without printing the key:

```bash
sudo awk -F= '
  $1=="CONTROL_PLANE_API_KEY" {print "CONTROL_PLANE_API_KEY=SET"}
  $1=="X_READER_DB_PATH" {print}
' /etc/x-reader-tunnel/env
```

Create `/etc/systemd/system/x-reader-tunnel.service`:

```bash
sudo tee /etc/systemd/system/x-reader-tunnel.service >/dev/null <<'EOF'
[Unit]
Description=x-reader Secure MCP Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/x-reader
EnvironmentFile=/etc/x-reader-tunnel/env
ExecStart=/usr/local/bin/tunnel-client run --profile-file /home/ubuntu/.config/tunnel-client/x-reader.yaml --health.listen-addr 127.0.0.1:8081
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Start and inspect it before enabling boot startup:

```bash
sudo systemctl daemon-reload
sudo systemctl start x-reader-tunnel
sleep 3
sudo systemctl --no-pager --full status x-reader-tunnel
```

Expected state:

```text
Active: active (running)
```

Readiness check:

```bash
curl -i http://127.0.0.1:8081/readyz
```

Known-good result:

```text
HTTP/1.1 200 OK

ready
```

Control Plane polling check:

```bash
curl -s http://127.0.0.1:8081/metrics \
  | grep -E 'commands_poll|control_plane'
```

The critical signal is that this gauge is non-zero:

```text
commands_poll_last_successful_timestamp_seconds
```

A known-good live run also showed `commands_poll_cycles_total > 0` and poll latency with `error="false"`. A roughly 30-second completed poll is not itself suspicious because the Control Plane uses long polling.

After the service is healthy, enable it on boot:

```bash
sudo systemctl enable x-reader-tunnel
systemctl is-enabled x-reader-tunnel
systemctl is-active x-reader-tunnel
```

Expected:

```text
enabled
active
```

At this point the SSH session can be closed. systemd keeps the tunnel alive independently.

Useful operator commands:

```bash
# status
systemctl status x-reader-tunnel

# last 100 log lines
sudo journalctl -u x-reader-tunnel -n 100 --no-pager

# follow logs live
sudo journalctl -u x-reader-tunnel -f

# restart
sudo systemctl restart x-reader-tunnel

# stop
sudo systemctl stop x-reader-tunnel

# readiness
curl -fsS http://127.0.0.1:8081/readyz && echo

# control-plane polling signal
curl -s http://127.0.0.1:8081/metrics \
  | grep -E 'commands_poll|control_plane'
```

Operational chain after reboot or SSH logout:

```text
systemd
  -> tunnel-client
  -> x-reader-mcp
  -> ChatGPT plugin
```

## Deferred cleanup

Not required for current production use:

- slim large media payloads only after inspecting real `twscrape` payload shapes
- decide whether REST and MCP need a shared cross-process rate budget
- optionally document or automate SSH port-forward access to `/ui`

Keep the implementation bounded. The current architecture is already sufficient for the intended single-user read-only workflow.
