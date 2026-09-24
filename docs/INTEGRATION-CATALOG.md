# Integration Catalog: Stable BizGPT Tool Contracts

These contracts are what the BizGPT Agent sees. They are served by `bizgpt-mcp` (one MCP Streamable HTTP server). **Contract names and argument shapes are versioned (`v1`) and must not change on a provider swap.** A breaking change means adding `_v2` and keeping `v1` for one release.

Common rules:
- Every call is scoped to the calling user (resolved from `X-OpenWebUI-User-Id`).
- Errors return `{ "error": { "code": "...", "message": "...", "action": "connect_integration|retry|fix_input" } }`.
- Write actions (`send_*`, `archive_*`, `submit_form`, `run_workflow` when flagged `requires_confirmation`) need `confirm: true`. Without it, the tool returns a preview.
- IDs are opaque strings prefixed by provider (`gmail:…`, `graph:…`) so the gateway can route them.

## Email: `EmailProvider` (Gmail MCP | ms-365 MCP)

| Contract | Args | Gmail MCP (to be confirmed) / google_workspace_mcp | ms-365-mcp |
|---|---|---|---|
| `search_emails` | `query, account?, limit=20, unread_only?` | search messages | `list-mail-messages` ($search / $filter) |
| `get_email` | `email_id` | get message | `get-mail-message` |
| `send_email` | `to[], subject, body, cc?, bcc?, confirm` | send | `send-mail` |
| `reply_email` | `email_id, body, reply_all=false, confirm` | reply | `reply-mail-message` / `reply-all-mail-message` |
| `forward_email` | `email_id, to[], comment?, confirm` | forward | `forward-mail-message` |
| `draft_email` | `to[], subject, body, reply_to_id?` | create draft | `create-draft-email` |
| `archive_email` | `email_ids[], confirm` | remove INBOX label | `move-mail-message` → Archive |
| `mark_email` | `email_ids[], read: bool` | modify UNREAD label | PATCH `isRead` |
| `list_labels` / `label_email` | `email_ids[], add[], remove[]` | labels | categories / folders |
| `list_email_accounts` | | Nango connections for google-mail | Nango connections for microsoft |

## Workflows: `WorkflowProvider` (Dify Service API)

| Contract | Args | Dify |
|---|---|---|
| `get_workflows` | `tag?` | BizGPT registry (`config/workflows.yaml`), filtered by the user's groups, plus `/v1/info` |
| `get_workflow` | `workflow_id` | `/v1/info` + `/v1/parameters` → JSON Schema of inputs |
| `run_workflow` | `workflow_id, inputs{}, wait=true, confirm?` | `POST /v1/workflows/run` (blocking or streaming) |
| `get_workflow_run` | `run_id` | `GET /v1/workflows/run/{id}` → status, outputs, error, elapsed |
| `stop_workflow_run` | `task_id` | `POST /v1/workflows/tasks/{task_id}/stop` |

## Forms: `FormsProvider` (BizGPT forms service)

| Contract | Args | Notes |
|---|---|---|
| `get_form_types` | | Registry: `config/forms/*.json` plus auto-generated forms for Dify workflows |
| `create_form` | `form_type, prefill{}` | Returns `form_id`, `missing_fields[]`, `url` |
| `get_form` | `form_id` | Status: `draft`, `submitted`, `executed` or `failed`, plus values and result |
| `submit_form` | `form_id, values{}, confirm` | Server-side JSON Schema validation, then runs the form's action |

Open WebUI Tool `bizgpt_forms.show_form(form_id)` shows the form in the chat as an HTML embed. It is the only piece that must be an Open WebUI Tool, because MCP results can't return embeds.

## WhatsApp: `WhatsAppProvider` (BizGPT whatsapp-gateway → Meta Cloud API)

| Contract | Args | Notes |
|---|---|---|
| `send_whatsapp` | `to, text? , template?{name, lang, params}, media_url?, confirm` | Outside the 24-hour window, only templates are allowed (Meta rule) |
| `get_whatsapp_messages` | `contact?, since?, limit=50` | From the gateway's message store (webhook-fed) |
| `list_whatsapp_templates` | | Graph `message_templates` |

## Integrations: `IntegrationProvider` (Nango)

| Contract | Args | Nango |
|---|---|---|
| `get_integration_status` | `integration?` | `GET /connection?connectionId=<user>` → connected / expired / missing |
| `connect_integration` | `integration` | `POST /connect/sessions` (end_user = user id) → Connect UI link |
| `disconnect_integration` | `integration, confirm` | `DELETE /connection/{id}` |

## Inbox (BizGPT-native Inbox Zero, Phase 6)

`get_inbox_summary`, `triage_inbox`, `create_email_rule`, `list_email_rules`, `bulk_unsubscribe_suggestions`. They are built on top of the Email contracts, not on a provider.

## Upstream connections (managed by `sync.py`, not called by the Agent directly)

| id | URL (internal) | Type | Auth |
|---|---|---|---|
| `bizgpt` | `http://bizgpt-mcp:8000/mcp` | MCP | bearer `BIZGPT_MCP_KEY` + forwarded user headers |
| `gmail-upstream` | internal only, called by the gateway | MCP | per-user bearer from Nango |
| `ms365-upstream` | `http://ms365-mcp:3000/mcp` | MCP | per-user bearer from Nango |
