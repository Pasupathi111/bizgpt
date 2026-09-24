# BizGPT Architecture

## 1. Principles

1. **Open WebUI is an upstream dependency.** Run the official image, pinned (`OPEN_WEBUI_VERSION`). Target: **0 core modifications**.
2. **Only supported extension points:** HTTP API, MCP, OpenAPI tool servers, Functions (Pipe/Filter/Action), Tools, env config. **No `from open_webui…` imports** in any BizGPT service.
3. **Stable tool contracts.** The AI calls `search_emails` or `run_workflow`, never `gmail.users.messages.list`. Providers sit behind interfaces.
4. **Reuse before build,** following the decision order in the master instruction and the evidence in GITHUB-REUSE-ANALYSIS.md.
5. **Nango owns OAuth tokens.** No integration stores refresh tokens itself.
6. **Git is the source of truth.** `sync.py` makes Open WebUI match the repo, idempotently.

## 2. Target topology

```text
                              Browser
                                 │  HTTPS
                        ┌────────┴─────────┐
                        │  Reverse proxy   │  (Caddy / nginx)
                        │  /        → OWUI │
                        │  /dashboard → UI │
                        │  /forms   → UI   │
                        └──┬─────────┬─────┘
                           │         │
          ┌────────────────┘         └──────────────────┐
          ▼                                             ▼
┌───────────────────────┐                   ┌───────────────────────┐
│ Open WebUI (upstream) │                   │ BizGPT Dashboard      │
│ ghcr image, pinned    │                   │ React/Vite/shadcn     │
│                       │                   └──────────┬────────────┘
│ • BizGPT Agent model  │                              │ HTTP (user's OWUI token)
│ • dify_pipe (Pipe)    │                              ▼
│ • forms tool (Tool)   │                   ┌───────────────────────┐
│ • audit filter        │                   │ bizgpt-api (FastAPI)  │
└──────────┬────────────┘                   │ dashboard BFF         │
           │ MCP Streamable HTTP            └──────────┬────────────┘
           │ + bearer key + X-OpenWebUI-User-* headers │
           ▼                                           │
┌──────────────────────────────────────────────────────┴───────────┐
│ bizgpt-mcp  (BizGPT MCP gateway: FastMCP, Python)                │
│ STABLE CONTRACTS: search_emails, get_email, send_email, …        │
│                   get_workflows, run_workflow, get_workflow_run  │
│                   create_form, get_form, submit_form             │
│                   send_whatsapp, get_whatsapp_messages           │
│                   get_integration_status, connect_integration    │
│  ┌─────────────┬──────────────┬────────────┬──────────────────┐  │
│  │EmailProvider│WorkflowProv. │FormsProv.  │WhatsAppProvider  │  │
│  │ Gmail|Graph │ Dify         │ forms svc  │ wa-gateway       │  │
└──┴──────┬──────┴──────┬───────┴─────┬──────┴────────┬─────────┴──┘
          │             │             │               │
   ┌──────┴──────┐      │             │               │
   ▼             ▼      ▼             ▼               ▼
Gmail MCP   ms-365 MCP  Dify      forms service   whatsapp-gateway ──► Meta Cloud API
(existing / (Softeria)  (self-    (FastAPI +      (FastAPI; webhook      ▲
 workspace-             hosted)    rjsf UI)        receiver + store)     │ webhooks
 mcp)                                                                     │
   ▲             ▲                                                        │
   └──── bearer token per user ◄──── Nango (Auth + Proxy, self-hosted) ◄──┘ (Meta token
                                     connection_id = OWUI user id           in Nango or env)
```

## 3. Identity and multi-user flow

1. The user signs in to Open WebUI (SSO recommended).
2. Open WebUI calls `bizgpt-mcp` with:
   - `Authorization: Bearer <BIZGPT_MCP_KEY>` (connection `auth_type: bearer`), and
   - `X-OpenWebUI-User-Id`, `X-OpenWebUI-User-Email`, `X-OpenWebUI-Chat-Id` (with `ENABLE_FORWARD_USER_INFO_HEADERS=true`).
3. The gateway **trusts the user headers only when the bearer key matches** and the request comes from the internal Docker network. The gateway is never exposed publicly.
4. The gateway resolves `connection_id = user_id` in Nango. It gets a fresh access token (Nango refreshes it) or proxies the call through Nango.
5. It forwards the token to the upstream MCP as `Authorization: Bearer …`. Both ms-365-mcp (`--http`, stateless) and google_workspace_mcp (external OAuth mode) support this.
6. If there is no connection, `connect_integration` returns a **Nango Connect link**, which the chat shows as a button.

## 4. Component decisions

| Capability | Decision | Type | Reuse |
|---|---|---|---|
| Chat UI, users, RBAC, analytics | Open WebUI | Upstream | 100% |
| Branding | `WEBUI_NAME`, logo/favicon asset override, `WEBUI_BANNERS` | Configuration | **Licence-gated** (audit §6) |
| Gmail | Existing Gmail MCP (**to be located**), else `google_workspace_mcp` | MCP (upstream) | 100% |
| Outlook | `Softeria/ms-365-mcp-server --http --preset mail` | MCP (upstream) | 100% |
| OAuth / tokens | Nango free self-hosted (Auth + Proxy) | External service | 100% |
| WhatsApp | **Build** `services/whatsapp-gateway` on the official Cloud API | External FastAPI service | Patterns from tkhattar14 (MIT) |
| Dify | Workflow registry, then the Dify Service API behind `run_workflow`; keep `dify_pipe` for "app as model" | MCP contract + Function | Dify API 100% |
| Dynamic Forms | **Build** `services/forms` (FastAPI, Pydantic, JSON Schema) with a React `@rjsf/shadcn` renderer; in chat via a Python Tool that returns an `HTMLResponse` embed | External service + Tool | rjsf |
| Dashboard | **Build** `dashboard/` (React, Vite, Tailwind, shadcn, Lucide) with `bizgpt-api` as its backend-for-frontend (BFF) | External app | Open WebUI analytics API |
| Inbox Zero | **Decision D:** BizGPT-native triage (see §6) | MCP contract + service | Our email contracts |
| Agent | Open WebUI **custom model** "BizGPT Agent": base model, system prompt, native function calling, `bizgpt-mcp` attached. Defined in Git (`owui/models/`) | Configuration (Models API) | 100% Open WebUI |

## 5. Dynamic Forms flow

```text
User: "Book a cab tomorrow at 10 AM"
  → Agent picks form type "cab_booking" (from forms registry via get_form_types)
  → Agent extracts known fields {date: 2026-09-26, time: 10:00}
  → create_form(type, prefill) → forms service validates the prefill against JSON Schema,
    returns {form_id, missing: [pickup, destination, vehicle], url}
  → Tool `bizgpt_forms.show_form(form_id)` returns HTMLResponse (iframe /forms/f/<id>)
    - short forms: request:user_input dialog instead (native Open WebUI)
  → User completes → rjsf client validation → POST /forms/<id>/submit
  → server validation (same schema) → confirmation screen → submit
  → execute action: Dify workflow | webhook | email | WhatsApp (per form definition)
  → result written back; agent reads it with get_form(form_id)
```

Dify's `GET /v1/parameters` converts to JSON Schema, so **every Dify workflow automatically gets a form.**

**Spike needed:** how the embed's submit notifies the running chat. The candidates are a `postMessage` bridge versus polling `get_form`.

## 6. Inbox Zero decision

| Option | Licence | Nango / Gmail MCP fit | Effort | Verdict |
|---|---|---|---|---|
| A. External Inbox Zero service | Needs Inbox Zero enterprise licence (5+ users) | ❌ own OAuth; users connect twice | Low | Only with licence |
| B. Reuse selected components | AGPL-3.0 + extra terms; makes BizGPT AGPL-derived | ❌ | High | **Rejected** |
| C. Integrate its APIs / MCP | Same licence as A | ❌ | Low–medium | Only with licence (pairs with A) |
| **D. BizGPT-native Inbox Zero** | Ours | ✅ uses our email contracts, Nango, Dify | Medium | **Recommended** |

D scope (MVP): AI triage labels, "needs reply" detection, draft replies, bulk archive / unsubscribe suggestions, daily digest, and rules stored as JSON. It's built as contracts (`triage_inbox`, `get_inbox_summary`, `create_email_rule`) in `bizgpt-mcp` plus an "Inbox" dashboard page. Heavy processing can run as Dify workflows.

## 7. Repository layout (target)

```text
bizgpt/
├── docker-compose.yml            # prod stack, all images pinned
├── docker-compose.test.yml       # temporary upgrade-test environment
├── .env.example
├── config/                       # workflows.yaml, forms/*.json, integrations.yaml
├── owui/
│   ├── functions/                # dify_pipe.py, audit_filter.py, …
│   ├── tools/                    # bizgpt_forms.py (HTML embed)
│   ├── models/                   # bizgpt-agent.json
│   ├── tool_servers.json         # MCP connections (templated from env)
│   └── banners.json, prompts/
├── services/
│   ├── mcp-gateway/              # bizgpt-mcp: stable contracts + providers
│   ├── forms/                    # FastAPI + web/ (React, rjsf-shadcn)
│   ├── whatsapp-gateway/
│   └── api/                      # dashboard BFF
├── dashboard/                    # React/Vite/shadcn
├── mcp/                          # upstream MCP deploy config (ms-365, gmail)
├── scripts/                      # sync.py, upgrade.sh, compatibility-check.sh, backup.sh
├── tests/                        # smoke + contract tests
└── docs/
```
