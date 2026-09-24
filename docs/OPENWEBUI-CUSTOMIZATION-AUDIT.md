# Open WebUI Customization Audit

Audit date: 2026-09-25. Scope: `/Users/sathya/DBiz/BizGPT/open-webui/` and `/Users/sathya/DBiz/BizGPT/bizgpt/`.

## 1. Summary

| Check | Result |
|---|---|
| Open WebUI core modifications | **0.** `git status` in `open-webui/` is clean. |
| BizGPT code importing `open_webui.*` internals | **None.** `grep -rn "from open_webui\|import open_webui" bizgpt/` returns nothing. |
| BizGPT in version control | **No.** `bizgpt/` is not a git repository yet. It must be before Phase 1 ends. |
| Secrets committed | None (no repo). `bizgpt/.env` holds only local demo placeholders, and `.gitignore` already excludes `.env`. |
| Verdict | Upgrade-safe baseline. Every existing customization uses a supported extension point. |

## 2. Upstream Open WebUI

| Item | Value |
|---|---|
| Repository | https://github.com/open-webui/open-webui |
| Local path | `open-webui/` (reference only; production does not build from it) |
| Version | `v0.11.4` (`package.json` → `0.11.4`; latest release, 2026-09-21) |
| Git commit | `8bd8b4fac5e059578ac0c74b3c18d11139f88b7d` (branch `main`, tag `v0.11.4`) |
| Working tree | Clean, no local changes |
| Docker image (pulled locally) | `ghcr.io/open-webui/open-webui:v0.11.4` (5.86 GB) |
| Licence | Open WebUI License (BSD-3 plus a **branding clause**, see §6) |

## 3. Existing customizations in `bizgpt/`

| Path | What it is | Classification | Upgrade-safe? | Notes |
|---|---|---|---|---|
| `owui/functions/dify_pipe.py` | Manifold **Pipe** that shows each Dify app as a model. Streams text, shows node progress as status events, emits citations, maps chat to Dify conversation | **Function (Pipe)** | Yes. Uses only the documented Pipe contract (`pipes()`, `pipe(body, __user__, __event_emitter__, __chat_id__, __task__)`) plus `aiohttp` and `pydantic` | Tested against a mock Dify outside Open WebUI; not yet tested inside Open WebUI or against real Dify. In the target architecture it stays as an **optional "Dify app as model" showcase**. The primary Dify path moves to the stable `run_workflow` contract (see ARCHITECTURE.md). |
| `scripts/sync.py` | Pushes `owui/functions` and `owui/tools` through the REST API and sets valves from `.env` | **Deployment tooling** (uses HTTP API) | Yes | Idempotent for functions and tools (GET, then create or update). **Gaps:** no MCP/tool-server config, models (agent), prompts, banners or groups; no dry-run; env names use `OWUI_*` instead of `OPEN_WEBUI_*`. |
| `docker-compose.yml` | Runs the official image, pinned via `${OWUI_VERSION:-v0.11.4}` | **Configuration** | Yes | Rename to `OPEN_WEBUI_VERSION` and **remove the default** so a missing pin fails loudly. No Postgres, Redis or reverse proxy yet. |
| `.env.example`, `.env` | Environment | **Configuration** | Yes | `.env` contains local demo values only. |
| `demo/dify/lead-qualifier.yml` | Dify DSL app for demos | **External (Dify) asset** | N/A | Imported into Dify, not Open WebUI. |
| `demo/dify/sample-hr-policy.md` | Demo knowledge document | Demo asset | N/A | |
| `dev/mock_dify.py` | Fake Dify SSE API for offline tests | **Dev tooling** | N/A | Keep for CI compatibility tests. |
| `README.md`, `DEMO.md` | Docs | Docs | N/A | Update after the architecture is approved. |
| `services/`, `dashboard/`, `mcp/` | Not created yet | n/a | n/a | |

## 4. Feature inventory

| Feature | Current state | Found where |
|---|---|---|
| Functions (Pipe) | 1: `dify_pipe` | `bizgpt/owui/functions/` |
| Tools | **None** | |
| Actions | **None** | |
| Filters | **None** | |
| MCP configuration | **None** (no `TOOL_SERVER_CONNECTIONS`, no `bizgpt/mcp/`) | |
| BizGPT APIs / services | **None** | |
| Gmail MCP | **Not found on this machine.** See §5. | |
| Dify integration | Pipe function (above); Dify itself is self-hosted by DBiz (URL and version unknown) | |
| Nango | **None** | |
| WhatsApp | **None** | |
| Dynamic Forms | **None** | |
| Inbox Zero | **None** | |
| Dashboard | **None** | |
| Branding | Only `WEBUI_NAME=BizGPT` in `.env`. Open WebUI renders it as **"BizGPT (Open WebUI)"** (`env.py:951-953`). | |
| Frontend modifications | **None** | |
| Backend modifications | **None** | |

## 5. Blocker: "existing Gmail MCP"

No standalone Gmail MCP server exists on this machine (searched `/Users/sathya` and `/Users/Apple`; no project and no `mcpServers` entry in `~/.claude.json`).

The Gmail tools visible in this Claude session come from a **claude.ai Gmail connector**. Only Claude can use it, and **Open WebUI cannot call it**.

**We need from DBiz:** the location (repo URL or server URL), transport (stdio / SSE / streamable HTTP) and auth model (single account, or per-user OAuth / bearer token) of the Gmail MCP you mean.

If no reusable Gmail MCP exists, the recommended replacement is `taylorwilsdon/google_workspace_mcp` (MIT, about 3.2k stars, streamable HTTP, OAuth 2.1 multi-user, external bearer-token mode). See GITHUB-REUSE-ANALYSIS.md.

## 6. Branding: licence constraint

Open WebUI `LICENSE` clause 4 forbids altering, removing or replacing "Open WebUI" branding (name, logo, visual identifiers) unless one of these holds:

1. There are **50 or fewer end users** in any rolling 30 days, or
2. You have written permission, or
3. You hold an **enterprise licence** (Open WebUI reads it from `LICENSE_KEY`, `env.py:919-922`).

In code, `WEBUI_NAME` always gets the suffix " (Open WebUI)". A full "BizGPT" rebrand therefore needs **either a core modification (not allowed, and a licence breach) or an enterprise licence.**

**Decision needed:** buy an enterprise licence, or ship "BizGPT (Open WebUI)" co-branding.

## 7. Supported extension points available in v0.11.4 (verified in source)

These are what BizGPT builds on. None needs a core change.

| Extension point | Evidence | BizGPT use |
|---|---|---|
| Functions: Pipe / Filter / Action | `backend/open_webui/functions.py` | Dify-as-model; audit and PII filters; "Send via WhatsApp" action |
| Tools (Python) returning `HTMLResponse` embeds | `utils/middleware.py:1061-1071` | Dynamic Forms rendered inline in chat |
| `__event_call__` with `request:user_input` (multiple-choice ask-user dialog) | `src/lib/components/chat/Chat.svelte:1402`, `AskUserCard.svelte` | Quick missing-field questions |
| MCP client (Streamable HTTP) | `utils/mcp/client.py` (`streamablehttp_client`) | BizGPT MCP gateway, ms-365 MCP, Gmail MCP |
| Tool server auth: `none`, `bearer`, `session`, `system_oauth`, `oauth_2.1`, `oauth_2.1_static`, plus **custom headers with user templating** | `utils/tools.py:146-175` | Per-user identity to the gateway |
| Forward user identity headers `X-OpenWebUI-User-Id/Email/Role` and `X-OpenWebUI-Chat-Id` | `env.py:991-998` (`ENABLE_FORWARD_USER_INFO_HEADERS`) | Map an Open WebUI user to a Nango connection |
| `TOOL_SERVER_CONNECTIONS` env and `/api/v1/configs/tool_servers` API | `config.py:378-388`, `routers/configs.py:235-240` | `sync.py` manages MCP connections |
| Config import/export | `routers/configs.py:100-118` | Backup before upgrade |
| Models API (custom "agent" models with tools and system prompt) | `routers/models.py:285` (`/create`), `/import`, `/export` | BizGPT Agent defined in Git |
| Analytics API | `routers/analytics.py`: `/summary`, `/daily`, `/tokens`, `/models`, `/users` | Dashboard "AI usage" |
| Banners | `WEBUI_BANNERS`, `/api/v1/configs/banners` | Link to the Dashboard from the chat UI |
| API keys | `ENABLE_API_KEYS` | `sync.py`, dashboard backend, compatibility checks |

## 8. Core modifications: none to migrate

No core modification exists, so no migration is needed. For completeness, these are the requirements that could tempt a core change, with the supported alternative for each:

| Tempting core change | Why it's tempting | Supported alternative |
|---|---|---|
| Replace "Open WebUI" name and logo | Full BizGPT rebrand | Enterprise `LICENSE_KEY`, or co-branding (§6) |
| Add a "Dashboard" item to the Open WebUI sidebar | Navigation | Separate app on the same domain (`/dashboard`) behind the reverse proxy, plus a **banner link** and a model / prompt suggestion link. **Tool:** no. **Function:** no. **External service:** yes. |
| Custom form widgets inside the chat | Dynamic Forms | Python **Tool** returning `HTMLResponse` (iframe to the forms service) plus the `request:user_input` event. **External service:** yes. |
| Provider logic in the backend (Gmail, Outlook, WhatsApp) | Integrations | **MCP** (BizGPT gateway plus upstream MCPs) |
| Custom analytics endpoints | Dashboard | Dashboard backend reads the Open WebUI **HTTP API** (`/api/v1/analytics/*`) |
