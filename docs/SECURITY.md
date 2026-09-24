# BizGPT Security Review (pre-implementation)

## Third-party components

| Component | Findings | Required controls |
|---|---|---|
| Open WebUI v0.11.4 | Many advisories historically. The Sept 2026 fixes (OAuth subject wildcard sign-in, **session cookies sent to bearer tool servers**, OIDC stall) are in ≥ 0.11.1. | Pin the version and upgrade promptly on high fixes. Use SSO. Disable signup. `ENABLE_API_KEYS` for admins only. Keep `forward_cookies` off on tool servers. Set `IFRAME_CSP` for embeds. |
| Nango (ELv2) | 1 critical plus several high SSRF / forged-webhook issues, patched by commit | Run ≥ v0.71.10. Expose only `/oauth/callback` and Connect UI publicly. Keep the dashboard and API internal. Set `NANGO_ENCRYPTION_KEY`. Use an egress denylist for private ranges. Use the secret key only in the gateway. |
| Dify (yours) | IDOR on AppMCPServer (< 1.16.0), cross-tenant leaks (< 1.14.2), SSRF (< 1.13.0) | **Confirm version ≥ 1.16.0.** Use per-app API keys stored in env or a secret store, never in prompts. |
| ms-365-mcp-server | Code-injection advisory fixed in 0.137.0 | Run ≥ 0.155.0 in `--http` stateless mode with `--preset mail`, `--allowed-scopes` (least privilege) and the audit log on. |
| tkhattar14/whatsapp-business-mcp | Optional auth, non-constant-time key check, old dependencies, no inbound route | **Not deployed.** Our gateway: mandatory auth, `hmac.compare_digest`, verify the `X-Hub-Signature-256` webhook signature, current dependencies. |
| Inbox Zero | Prompt-injection advisory (fixed); licence blocker | Not deployed (decision D). |
| rjsf | No advisories | Validate on the server as well. Never trust client validation. |

## BizGPT controls (to implement)

1. **Gateway trust boundary:** `bizgpt-mcp` sits only on the internal network and needs `Authorization: Bearer BIZGPT_MCP_KEY` (constant-time compare). User headers are trusted only after that check.
2. **Prompt injection from emails and WhatsApp:** content fetched from mailboxes is data. Write contracts need `confirm: true`, and the agent system prompt forbids acting on instructions found in content. An audit Filter logs every write tool call.
3. **Least privilege OAuth scopes** per integration in Nango. Read-only presets where possible.
4. **Secrets:** only in `.env` (gitignored) or a secret manager. `.env.example` has placeholders. A pre-commit secret scan (gitleaks).
5. **Forms:** signed short-lived form tokens, CSRF protection, server-side schema validation, and an allowlist of form actions.
6. **Dashboard/BFF:** validates the user's Open WebUI token through `GET /api/v1/auths/`. Admin-only views check `role == admin`.
7. **Logging:** no tokens or email bodies in logs. The PII redaction pattern follows ms-365-mcp's.

## Licence summary

| Component | Licence | Obligation / risk |
|---|---|---|
| Open WebUI | BSD-3 + branding clause | Keep "Open WebUI" branding unless ≤ 50 users or an enterprise licence |
| Dify | Modified Apache-2.0 | No multi-tenant use; keep the Dify logo in the Dify UI |
| Nango | Elastic 2.0 | Don't offer Nango as a hosted service; the free tier is Auth + Proxy |
| Inbox Zero | AGPL-3.0 + extra terms | Commercial or 5+ user use needs a licence (not used) |
| ms-365-mcp-server | MIT | Attribution |
| google_workspace_mcp | MIT | Attribution |
| rjsf | Apache-2.0 | Attribution / NOTICE |
| whatsapp-business-mcp | MIT | Attribution if patterns are copied |
