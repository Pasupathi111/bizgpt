# GitHub / Open-Source Reuse Analysis

Data collected 2026-09-25 from the GitHub REST API (stars, issues, activity, advisories), raw LICENSE files, and a source review of shallow clones in `/Users/sathya/DBiz/BizGPT/reference/`. The clones are for review only; nothing is vendored into `bizgpt/`.

"Open issues" is GitHub's `open_issues_count`, which includes open PRs.

## 1. Scorecard

| Repository | Licence | ★ | Open issues | Last push | Latest release | Advisories (all time) | Verdict |
|---|---|---|---|---|---|---|---|
| [open-webui/open-webui](https://github.com/open-webui/open-webui) | Biz GPT License (BSD-3 + branding clause) | 153,076 | 311 | 2026-09-24 | v0.11.4 (2026-09-21) | 100+ fetched (1 critical, 40 high); recent ones fixed in 0.11.1 | **Upstream platform. Pin the version.** |
| [Softeria/ms-365-mcp-server](https://github.com/Softeria/ms-365-mcp-server) | MIT | 994 | 6 | 2026-09-22 | v0.155.0 (2026-09-22) | 1 high (fixed in 0.137.0) | **Adopt** for Outlook |
| [tkhattar14/whatsapp-business-mcp](https://github.com/tkhattar14/whatsapp-business-mcp) | MIT | 3 | 1 | 2026-03-28 (single commit) | none | 0 (never reviewed) | **Do not deploy.** Use as a reference only; build a small gateway. |
| [langgenius/dify](https://github.com/langgenius/dify) | Modified Apache-2.0 | 157,119 | 1,104 | 2026-09-24 | 1.17.1 (2026-09-10) | 21 (8 high) | **Integrate via its Service API** (already self-hosted) |
| [NangoHQ/nango](https://github.com/NangoHQ/nango) | **Elastic License 2.0** | 12,325 | 129 | 2026-09-24 | v0.71.10 (2026-09-21) | 10 (1 critical, 7 high; several patched only by commit) | **Adopt for Auth + Proxy only.** The free tier has no MCP or tools. |
| [elie222/inbox-zero](https://github.com/elie222/inbox-zero) | **AGPL-3.0 + commercial restriction** | 12,327 | 151 | 2026-09-24 | continuous | 2 (medium, low) | **Licence blocker.** See §7. |
| [rjsf-team/react-jsonschema-form](https://github.com/rjsf-team/react-jsonschema-form) | Apache-2.0 | 15,904 | 112 | 2026-09-24 | v6.10.1 (2026-09-16) | 0 | **Adopt** (`@rjsf/shadcn` theme) |
| [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) (alternative) | MIT | 3,222 | 201 | 2026-09-24 | continuous | 0 | **Fallback Gmail MCP** if the existing one can't do multi-user |
| [FredShred7/whatsapp-mcp-server](https://github.com/FredShred7/whatsapp-mcp-server) (alternative) | MIT | 23 | 0 | 2026-06-07 | none | 0 | Small; not reviewed in depth; same concern as tkhattar14 |
| [YanxingLiu/dify-mcp-server](https://github.com/YanxingLiu/dify-mcp-server) (alternative) | none | 280 | n/a | 2025-04-20 | n/a | n/a | **Reject:** no licence, stale, and Dify now has native MCP |

## 2. Biz GPT (platform)

- **Architecture:** FastAPI backend and SvelteKit frontend in one image. Extension points are listed in the audit, §7.
- **Docker:** official `ghcr.io/open-webui/open-webui:<tag>`.
- **MCP:** native Streamable HTTP client. **OpenAPI:** native tool servers.
- **Auth:** local accounts, OIDC/OAuth SSO, LDAP, SCIM, API keys. **Multi-user:** yes (groups, RBAC).
- **Security:** high advisory volume. The Sept 2026 batch (OAuth subject wildcard sign-in, cookie forwarding to tool servers, OIDC stall) is **fixed in 0.11.1+**, so v0.11.4 includes those fixes. **Policy: track advisories every release; `upgrade.sh` is the path.**
- **Production suitability:** yes, with Postgres, Redis, HTTPS and a pinned version.
- **Without forking:** yes.

## 3. Outlook: Softeria/ms-365-mcp-server

- **Architecture:** TypeScript MCP server generated from the Microsoft Graph OpenAPI spec. Tool presets (`--preset mail`), a regex allowlist (`--enabled-tools`), `--read-only`, and a scope boundary (`--allowed-scopes`).
- **Mail tool coverage (verified in `src/endpoints.json`):** `list-mail-messages`, `get-mail-message`, `send-mail`, `reply-mail-message`, `reply-all-mail-message`, `forward-mail-message`, `create-draft-email`, `move-mail-message` (archive), `list-mail-folders`, attachments, rules and shared mailboxes. This covers our email contract.
- **Docker:** yes (`Dockerfile`, `Dockerfile.ghcr`). **MCP:** stdio and **Streamable HTTP** (`--http`).
- **Auth:** OAuth 2.1 with dynamic client registration, **per-request bearer token (stateless)**, On-Behalf-Of (`--obo`), or BYOT `MS365_MCP_OAUTH_TOKEN`.
- **Multi-user:** yes. HTTP mode is stateless per user.
- **Biz GPT compatibility:** the README has an explicit Biz GPT section (MCP Streamable HTTP plus OAuth 2.1).
- **Security:** one high advisory (code injection via `MS365_MCP_AUTH_CACHE_COMMAND`), patched in 0.137.0; the current version is 0.155.0. It has a structured audit log and PII redaction by default.
- **Production suitability:** good. **Effort:** low (an Azure app registration plus config).
- **Without forking:** yes.
- **Fit with Nango:** the gateway fetches the user's Microsoft token from Nango and passes it as a bearer, so Nango owns refresh.

## 4. WhatsApp: tkhattar14/whatsapp-business-mcp (source reviewed)

- **Architecture:** Python. `main.py` is a FastMCP server with **stdio only**. `main_http.py` is a **plain FastAPI REST API, not MCP**. There are 8 handlers (messaging, templates, media, analytics, flows, webhooks, business profile, account) in about 4.9k lines of code. It calls only `graph.facebook.com`, the official Cloud API, which is good.
- **Problems found in review:**
  1. **No MCP over HTTP.** Biz GPT can't use stdio servers directly. It pins `mcp==1.6.0`, which predates Streamable HTTP.
  2. **Auth is optional:** if `MCP_API_KEY` is unset, all `/api/*` routes are open. The key comparison uses `!=`, which is not constant-time.
  3. **No inbound messages.** There is a webhook signature helper (`hmac.compare_digest`, which is correct), but **no webhook receive route and no message store**, so `get_whatsapp_messages` is impossible.
  4. **Outdated pinned dependencies** (`fastapi 0.109.2`, `aiohttp 3.9.3`, `uvicorn 0.27.1`), with known CVEs in that aiohttp line.
  5. Single author, 3 stars, one commit, no tests, no releases.
  6. Single-tenant: one global `META_ACCESS_TOKEN`.
- **Verdict:** not production-suitable. Following the rule "if the existing repository is not production-suitable after security review, build a small BizGPT WhatsApp gateway", we **build `services/whatsapp-gateway`** on the official Cloud API. From this repo we reuse **only patterns**, with MIT attribution: the HMAC webhook verification, phone-number validation and error sanitisation.
- **Scope:** send text, template, media and interactive messages; receive webhook messages; store messages; expose them through the MCP gateway (`send_whatsapp`, `get_whatsapp_messages`).

## 5. Dify: langgenius/dify (your self-hosted instance)

- **Service API, verified in `api/controllers/service_api/app/`:**

| Need | Endpoint |
|---|---|
| Get workflow (metadata) | `GET /v1/info`, `GET /v1/meta` |
| Get workflow **input schema** | `GET /v1/parameters` (lets us auto-generate Dynamic Forms) |
| Run workflow | `POST /v1/workflows/run`, or `POST /v1/workflows/{workflow_id}/run` for a pinned version |
| Track status | `GET /v1/workflows/run/{workflow_run_id}`, `GET /v1/workflow/{run_id}/events` |
| Stop | `POST /v1/workflows/tasks/{task_id}/stop` |
| History / logs | `GET /v1/workflows/logs` |
| Human-in-the-loop form | `GET/POST /v1/form/human_input/{form_token}` |
| Chat apps | `POST /v1/chat-messages` |

- **"List workflows" gap:** Service API keys are **per app**. No service endpoint lists every app; that is only in the console API, which is internal and session-authenticated. **Solution:** a BizGPT **workflow registry** (`bizgpt/config/workflows.yaml`: id, name, key reference, tags, allowed groups), enriched at runtime from `/v1/info` and `/v1/parameters`.
- **Native MCP:** Dify can publish an app as an MCP server (`/mcp/server/<code>/mcp`, `api/controllers/mcp/mcp.py`). This is useful for quick demos, but it is one server per app and gives no stable contract, so it is **not** the primary path.
- **Licence:** modified Apache-2.0. **No multi-tenant use** (one workspace per tenant) without a commercial licence, and the Dify logo must stay in the Dify web UI. Using Dify as a backend over the API is explicitly allowed.
- **Security:** 8 high advisories, including an IDOR on AppMCPServer (fixed in **1.16.0**) and cross-tenant file preview (fixed in 1.14.2). **Action: confirm your Dify is ≥ 1.16.0** (latest is 1.17.1).
- **Without forking:** yes.

## 6. Nango: NangoHQ/nango

- **Licence: Elastic License 2.0.** You may not offer Nango itself **to third parties as a hosted/managed service**. Using it as internal plumbing inside BizGPT is normally fine, but **get a legal check if BizGPT is sold as SaaS to clients**.
- **Free self-hosted features (from `docs/guides/platform/free-self-hosting.mdx`):**

| Feature | Free self-hosted | Cloud / BYOC (paid) |
|---|---|---|
| API Auth (OAuth, token refresh, connections) | ✅ | ✅ |
| Proxy (authenticated API calls) | ✅ | ✅ |
| Syncs, tool calls, webhooks, triggers | ❌ | ✅ |
| **MCP server** | ❌ | ✅ |
| Custom auth branding, RBAC, MFA, SSO | ❌ | ✅ |

  The doc describes free self-hosting as "intended for hobby projects and evaluation".
- **Consequence for BizGPT:** Nango does exactly what we asked it to do (OAuth, tokens, refresh, connections, per-user mapping) through **Auth + Proxy**, which is free. It **cannot** be our MCP/tool layer unless we pay. Our MCP gateway calls providers through the Nango **proxy**, or fetches the token from Nango and forwards it to upstream MCPs.
- **Multi-user:** connection per `(integration, connection_id)`; we use `connection_id = <Biz GPT user id>`. Nango's Connect UI handles the OAuth consent screens.
- **Docker:** single image, bundled Postgres and Redis. Production needs external Postgres and Redis, `NANGO_ENCRYPTION_KEY` and an HTTPS server URL.
- **Security:** 1 critical (SSRF via connectionConfig template injection, "through v0.70.4", no fixed version listed) and 7 high (SSRF, proxy `base-url-override`, forged webhooks), mostly patched by commit. **Actions:** run ≥ v0.71.10; keep Nango **off the public internet** except `/oauth/callback` and Connect UI; set the proxy denylist; block egress to internal ranges.
- **Without forking:** yes.

## 7. Inbox Zero: elie222/inbox-zero (source reviewed)

- **Architecture:** a large Next.js and Turborepo monorepo (apps: `web`, `worker`, `desktop`, …). Needs Postgres (Prisma), Redis, its **own Google/Microsoft OAuth app** (`GOOGLE_CLIENT_ID`, `MICROSOFT_CLIENT_ID`) and an LLM key.
- **APIs:** REST `/api/v1`: `rules`, `rules/{id}`, `senders/unsubscribe`, `stats/by-period`, `stats/response-time`, `openapi.json`. Auth is an API key.
- **MCP server:** yes, `/mcp`, with OAuth (`mcp:read`, `mcp:write`). Tools: `search_inbox`, `read_thread`, `create_draft`, `list_rules`, `get_rule`, `create_rule`, `update_rule`, `delete_rule`, `get_stats_by_period`, `get_response_time_stats`, `list_email_accounts`. It needs `MCP_SERVER_ENABLED` and `NEXT_PUBLIC_EXTERNAL_API_ENABLED`, and integrations are tier-gated (`PLUS_MONTHLY`, bypassable with `NEXT_PUBLIC_BYPASS_PREMIUM_CHECKS` when self-hosted).
- **Our questions answered:**

| Question | Answer |
|---|---|
| Can we integrate it? | Technically yes, as an external service plus its MCP |
| Reuse its backend? | Only as a whole app; it isn't modular |
| Reuse its APIs? | Yes: REST v1 and MCP |
| Reuse selected modules? | Legally no without a licence (AGPL plus extra terms); the code is tightly coupled to Prisma and its auth |
| Work with our Gmail MCP? | **No.** It talks to the Gmail API directly with its own OAuth |
| Work with Nango? | **No.** It manages its own tokens, so users would connect Gmail twice |
| BizGPT-native UI on top? | Possible through its REST/MCP, but its own UI stays the primary one |

- **Licence (blocker):** AGPL-3.0 **plus** extra terms:
  - no monetising the software or including it in a commercial product sold for profit without written permission, and
  - **organisations with 5 or more business users must buy an enterprise licence.**

  BizGPT is a commercial enterprise product, so **any option (A, B or C) needs an Inbox Zero commercial licence.** Option B (copying modules) would also make BizGPT AGPL-derived.
- **Decision:** see ARCHITECTURE.md §6. **Recommend D** (BizGPT-native "Inbox Zero" features built on our email contracts, Nango and LLM), **unless** DBiz buys an Inbox Zero enterprise licence, in which case choose **A + C** (external service plus its MCP).

## 8. Dynamic Forms: rjsf-team/react-jsonschema-form

- **Licence:** Apache-2.0. 15.9k ★, active, 0 advisories.
- **`@rjsf/shadcn` v6.10.1** exists, using Tailwind v4, React ≥ 18 and tailwind-merge. This is exactly the requested stack (React, TypeScript, Tailwind, shadcn/ui).
- Validation with `@rjsf/validator-ajv8`. Server side, the same JSON Schema is validated with Pydantic and `jsonschema`, so the client and server agree.
- **Effort:** low for rendering. The real work is intent, prefill and the submit/execute pipeline, which BizGPT builds (as requested).

## 9. Gmail (existing MCP, not located)

The existing Gmail MCP must be identified (see the audit, §5). Requirements for it to be reusable in multi-user BizGPT:

1. Streamable HTTP (or SSE) transport.
2. It accepts a per-request user token (bearer), so Nango can own the tokens.
3. It covers search, get, send, reply, forward, draft, archive, read/unread and labels.

If it fails 1 or 2, use **`taylorwilsdon/google_workspace_mcp`**. It is MIT, has 0 advisories and 120+ tools (`--tools gmail`), and supports Streamable HTTP, OAuth 2.1 multi-user, stateless mode and **external OAuth provider mode (validates bearer tokens only)**. That last mode is the Nango fit.
