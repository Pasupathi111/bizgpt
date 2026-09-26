# Inbox Zero for Biz GPT

Self-hosted [Inbox Zero](https://github.com/elie222/inbox-zero) (release `v2.30.0`), served at
**https://test.gpt.dbizlab.com/inbox_zero** behind the existing nginx site.

Inbox Zero runs as its own Docker Compose project with its own Postgres and Redis; it is
not part of the Biz GPT `docker-compose.yml`. Everything here is deployment glue — no secrets.

| File | Purpose |
|---|---|
| `inbox-zero-base-path.patch` | Patch on top of `v2.30.0` so the app works under `/inbox_zero` |
| `docker-compose.override.yml` | Copy next to upstream `docker-compose.yml`: local image, localhost-only port, prefixed cron URLs |
| `nginx/inbox_zero_map.conf` | WebSocket `map` (goes in `sites-available`, enabled) |
| `nginx/test_gpt_locations.conf` | `location` blocks for the `test.gpt.dbizlab.com` HTTPS server |

## Why a patch

Upstream only runs at a domain root, and its `/api` routes collide with Biz GPT's. The patch
(10 files changed, 2 added) adds an optional Next.js `basePath` via `NEXT_PUBLIC_BASE_PATH`:

- `next.config.ts` — `basePath` from `NEXT_PUBLIC_BASE_PATH`; `docker/Dockerfile.prod` takes it as a build arg.
- `utils/base-path.ts` + `components/BasePathShim.tsx` — browser shim that prefixes hand-written
  `fetch("/api/...")` / `EventSource` URLs (Next.js already prefixes links and navigation).
- `new URL("/x", base)` → `new URL("./x", withTrailingSlash(base))` in 8 server files so redirects keep the prefix.
- better-auth: `baseURL` is `${NEXT_PUBLIC_BASE_URL}/api/auth`, and `app/api/auth/[...all]/route.ts`
  restores the prefix Next.js strips from route-handler URLs before better-auth matches the path.
- Sign-in success/error redirects (`callbackURL`, `errorCallbackURL`, `errorURL`, SSO) and the one
  `window.location.assign` get the prefix, since better-auth and the browser use them verbatim.

With `NEXT_PUBLIC_BASE_PATH` unset the app behaves exactly like upstream.

## Deploy

```bash
git clone https://github.com/elie222/inbox-zero.git /home/ubuntu/bizgpt-services/inbox-zero
cd /home/ubuntu/bizgpt-services/inbox-zero
git checkout -b bizgpt/base-path v2.30.0
git am /home/ubuntu/bizgpt/deploy/inbox-zero/inbox-zero-base-path.patch
cp /home/ubuntu/bizgpt/deploy/inbox-zero/docker-compose.override.yml .

cp apps/web/.env.example apps/web/.env   # fill in, see below; chmod 600
docker build -f docker/Dockerfile.prod --build-arg NEXT_PUBLIC_BASE_PATH=/inbox_zero \
  -t inbox-zero:2.30.0-bizgpt .
docker compose --profile all up -d
```

Root `.env` (compose interpolation only): `WEB_PORT=3010`, `POSTGRES_PORT=5434`,
`NEXT_PUBLIC_BASE_URL`, `POSTGRES_PASSWORD`, `UPSTASH_REDIS_TOKEN` (same values as in `apps/web/.env`).

`apps/web/.env` essentials:

- `NEXT_PUBLIC_BASE_URL=https://test.gpt.dbizlab.com/inbox_zero`
- `DATABASE_URL` / `DIRECT_URL` → `db:5432`, `UPSTASH_REDIS_URL=http://serverless-redis-http:80`, `REDIS_URL=redis://redis:6379`, `QUEUE_BACKEND=internal`
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — the Biz GPT Google OAuth client
- `GOOGLE_PUBSUB_TOPIC_NAME` — must exist for push notifications (not created yet)
- `AUTH_SECRET`, `EMAIL_ENCRYPT_SECRET`, `EMAIL_ENCRYPT_SALT`, `INTERNAL_API_KEY`, `API_KEY_SALT`, `CRON_SECRET`, `UPSTASH_REDIS_TOKEN` — `openssl rand -hex 32` (salt: `-hex 16`)
- `DEFAULT_LLM_PROVIDER=openai`, `DEFAULT_LLM_MODEL=gpt-5.4-mini`, `LLM_API_KEY`
- `AUTH_ALLOWED_EMAIL_DOMAINS=dbizsolution.com`, `AUTH_ALLOWED_EMAILS=dbizgpt.assistant@gmail.com` — restricts sign-up

Upstream template lines like `KEY= # comment` must be emptied (`KEY=`); Docker reads the comment as the value.

## Google OAuth redirect URIs

```
https://test.gpt.dbizlab.com/inbox_zero/api/auth/callback/google
https://test.gpt.dbizlab.com/inbox_zero/api/google/linking/callback
```

## Security

- Ports (3010 web, 5434 Postgres, 6380 Redis, 8079 Redis HTTP) are bound to `127.0.0.1`; only nginx is public.
- Inbox Zero keeps its `X-Frame-Options: DENY` / `frame-ancestors 'none'`; it is linked from Biz GPT, not iframed.
- Mailbox OAuth tokens stay in Inbox Zero's database, encrypted with `EMAIL_ENCRYPT_*`.
- Inbox Zero cannot reuse the Gmail MCP credentials; it signs users in with its own Google OAuth flow.

Google Cloud APIs that must be enabled in the OAuth project: People API, Gmail API (and Cloud Pub/Sub for push).
