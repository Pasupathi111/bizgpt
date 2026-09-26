# Upgrade Guide: Biz GPT

Goal: **upgrade Biz GPT → run the compatibility check → run sync.py → BizGPT still works**, with no code rewrites.

## Why it's safe

- There are no core modifications. BizGPT only uses the HTTP API, MCP, Functions and Tools, and env config.
- BizGPT services never import `open_webui`.
- Functions, Tools, models, MCP connections, banners and prompts live in Git and are re-applied by `sync.py`.
- The version is pinned (`OPEN_WEBUI_VERSION=v0.11.4`), never `latest`.

## Procedure

```bash
./scripts/upgrade.sh v0.11.5
```

`upgrade.sh` (built in Phase 1) does the following:

1. **Backup:** `docker compose exec` a DB dump (Postgres), a volume snapshot, `GET /api/v1/configs/export`, a `functions/export`, a `models/export` and `.env` → `backups/<timestamp>/`.
2. **Record** the current version (`backups/<ts>/VERSION`, `/api/version`).
3. **Pull** `ghcr.io/open-webui/open-webui:<new>`.
4. **Start a temporary test environment** (`docker-compose.test.yml`, project `bizgpt-upgrade-test`, port 3999) on a **copy** of the DB dump.
5. **Compatibility checks:** `scripts/compatibility-check.sh --target http://localhost:3999`.
6. **Sync Tools**, then 7. **sync Functions**: `sync.py --target test`.
8. **Validate MCP:** `POST /api/v1/configs/tool_servers/verify` for each connection.
9. **Validate integrations:** gateway `/health/integrations` (Nango, Dify, WhatsApp, ms-365, Gmail).
10. **UI/API smoke tests:** login, chat completion through the BizGPT Agent, a tool call, form embed render, dashboard API.
11. **All critical tests pass:** print `READY`, write `OPEN_WEBUI_VERSION=<new>` to `.env.next`, and ask for confirmation to switch production (`docker compose up -d`, then `sync.py`).
12. **Any critical test fails:** print `DO NOT DEPLOY` plus the failing checks, tear down the test env, and leave production untouched.

## Rollback

1. `OPEN_WEBUI_VERSION=<previous>` in `.env`.
2. Restore the DB from `backups/<ts>/` (Biz GPT migrations are forward-only, so a DB restore is **required** if the new version migrated the schema).
3. `docker compose up -d && python3 scripts/sync.py`.
4. `./scripts/compatibility-check.sh`.

## Release checklist (each new Biz GPT version)

- Read the release notes for changes to the **Functions/Tools API, MCP client, tool-server config schema, env var renames, and `request:user_input` / embeds**.
- Check GitHub security advisories fixed in this release. Prefer upgrading promptly when high or critical fixes land.
- Run `upgrade.sh`. Never skip the test environment.
