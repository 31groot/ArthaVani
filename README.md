# ArthaVani broker MCP integrations

ArthaVani keeps broker APIs behind MCP. LangGraph receives only broker-qualified,
read-only tools.

## Groww

Groww uses the existing local read-only MCP server and official `growwapi`
adapter. Its implementation is unchanged by the Zerodha self-hosting work.

## Zerodha Kite

ArthaVani uses the official Zerodha repository at
`https://github.com/zerodha/kite-mcp-server`, pinned during development to
commit `5e044dc` (current repository `master` at the time of setup).

The Python client builds and starts that checkout locally in HTTP mode:

```text
APP_MODE=http
APP_HOST=127.0.0.1
APP_PORT=8080
PUBLIC_BASE_URL=http://127.0.0.1:8080
```

The MCP endpoint is:

```text
http://127.0.0.1:8080/mcp
```

The official server's browser authentication routes are `/authorize` and
`/callback`; `PUBLIC_BASE_URL` is used to generate those browser-facing URLs.
Authentication is initiated through the official `login` MCP operation as an
application/session setup concern. It is not exposed to LangGraph.

Required local configuration, kept outside source control:

```bash
export KITE_API_KEY='your Kite Connect API key'
export KITE_API_SECRET='your Kite Connect API secret'
```

The official checkout is expected at `third_party/kite-mcp-server`. Set
`ZERODHA_KITE_SERVER_DIR` to override that path. The checkout requires Go
1.24.2 or newer; the current environment uses Go 1.25.5.

The server is configured defensively with these exclusions:

```text
place_order, modify_order, cancel_order,
place_gtt_order, modify_gtt_order, delete_gtt_order
```

The client applies a second read-only allowlist, and only namespaced
`zerodha_*` tools reach LangGraph.

Run the explicit local authentication diagnostic:

```bash
python -m tests.manual_zerodha_integration
```

The diagnostic connects, discovers tools, generates the login URL, waits for
browser authentication, then calls `get_profile` on the same MCP session. It
never prints credentials, tokens, cookies, or the full login response.
