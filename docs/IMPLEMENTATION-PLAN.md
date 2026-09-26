# Implementation Plan, Risks and Effort

## 1. Blockers: decisions needed before or at the start of Phase 1

| # | Blocker | Needed from DBiz | Blocks |
|---|---|---|---|
| B1 | **Branding licence.** A full "BizGPT" rebrand needs an Biz GPT enterprise licence (> 50 users) | Buy the licence, **or** accept "BizGPT (Biz GPT)" co-branding | Phase 1 branding |
| B2 | **Gmail MCP location unknown.** The only Gmail MCP found is the claude.ai connector, which Biz GPT can't use | Repo or URL, transport, and auth model of your Gmail MCP; or approval to use `google_workspace_mcp` | Phase 2 Gmail |
| B3 | **Inbox Zero licence.** AGPL plus a commercial / 5+ user restriction | Approve **option D** (native), or buy an Inbox Zero licence (then A + C) | Phase 6 |
| B4 | **Nango tier.** The free self-hosted tier is Auth + Proxy only ("hobby/evaluation"), and ELv2 forbids offering it as a hosted service | Accept the free tier (our gateway does the tools), or budget for BYOC; legal check if BizGPT is SaaS for clients | Phase 2 |
| B5 | **Dify details** | Dify URL, **version (must be ≥ 1.16.0)**, list of workflow apps with API keys | Phase 3 |
| B6 | **Meta WhatsApp Business** | Verified business, WABA, phone number ID, permanent system-user token, app secret, public HTTPS webhook URL | Phase 2 WhatsApp |
| B7 | **Azure app registration** for Outlook | Tenant ID, client ID and secret, redirect URI (configured in Nango) | Phase 2 Outlook |
| B8 | **Production host** | Server, domain, TLS, and Postgres/Redis (managed or containers) | Phase 1 deploy |

## 2. Implementation sequence

| Phase | Deliverables | Depends on | Effort (dev-days) |
|---|---|---|---|
| **1. Foundation** | `git init` for bizgpt; compose (Biz GPT pinned, Postgres, Redis, Caddy); `.env.example` (`OPEN_WEBUI_VERSION`); branding config; **sync.py v2** (functions, tools, models, tool servers, banners, prompts; idempotent; `--dry-run`, `--target`); **upgrade.sh**; **compatibility-check.sh**; DEPLOYMENT.md; CI smoke tests with `mock_dify` | B1, B8 | 6–8 |
| **2a. Nango** | Nango deploy, integrations config (google-mail, microsoft), Connect-link flow, `get_integration_status` / `connect_integration` | B4 | 3 |
| **2b. MCP gateway skeleton** | `services/mcp-gateway` (FastMCP, streamable HTTP, bearer auth, user resolution, provider interfaces, contract tests) | 2a | 4 |
| **2c. Gmail** | Plug the existing Gmail MCP (or workspace-mcp) behind `EmailProvider`; all email contracts | B2, 2b | 3 |
| **2d. Outlook** | ms-365-mcp deploy plus `GraphEmailProvider` | B7, 2b | 2–3 |
| **2e. WhatsApp** | `services/whatsapp-gateway` (send, webhook, store, templates) plus contracts | B6, 2b | 5–6 |
| **3. Dify** | Workflow registry, `get_workflows` / `get_workflow` / `run_workflow` / `get_workflow_run` / stop; keep `dify_pipe`; demo workflows | B5, 2b | 3–4 |
| **4. Dynamic Forms** | `services/forms` (FastAPI, Pydantic, JSON Schema, store, actions); `web/` (React, rjsf-shadcn); `bizgpt_forms` Tool (embed); Dify `/parameters` → form; embed→chat bridge spike; cab-booking demo | 3 | 8–10 |
| **5. Dashboard** | `services/api` BFF plus `dashboard/` (Overview, AI usage, Conversations, Workflows, Forms, Inbox, Integrations, Activity, Quick actions) | 1, 2a, 3, 4 | 8–10 |
| **6. Inbox (option D)** | Triage, needs-reply, digest, rules, bulk unsubscribe suggestions; Inbox dashboard page | 2c/2d, 5 | 8–10 |
| **7. BizGPT Agent** | `owui/models/bizgpt-agent.json` (system prompt, tools, native function calling); safety prompt; end-to-end scenarios; eval set | all | 4–5 |
| Hardening | Security controls in SECURITY.md, load test, runbooks, rollback drill | all | 4–5 |

**Total: about 58–71 dev-days**, which is roughly 12–14 weeks for one developer or 6–7 weeks for two in parallel. Once 2b exists, phases 2c–2e, 3 and 4 can run in parallel.

## 3. Technical risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Biz GPT changes the Functions/Tools or MCP config schema in a release | Medium | Medium | upgrade.sh test env, compatibility checks, pinned version |
| Form embed can't message the running chat | Medium | Low | Fallback: the agent polls `get_form`; the user types "done"; `request:user_input` for short forms |
| Existing Gmail MCP can't accept per-user bearer tokens | Medium | Medium | Swap in `google_workspace_mcp` behind the same contract |
| Nango free tier limits or licence change | Low–medium | Medium | Gateway abstracts `TokenProvider`; can swap to BYOC or direct OAuth |
| Prompt injection via inbound email / WhatsApp | High | High | Confirmation on writes, audit filter, content-as-data system prompt |
| Meta template approval and 24-hour window rules | High | Low | Template management and clear errors |
| Upstream MCP tool-name changes | Medium | Low | Stable contracts isolate the change to one provider file |
