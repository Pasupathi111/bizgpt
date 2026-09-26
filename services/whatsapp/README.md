# Biz GPT WhatsApp integration

A separate backend that connects the **Meta WhatsApp Cloud API** to **Biz GPT** (our Open WebUI).
Customers message your WhatsApp Business number; a Biz GPT agent answers them.

```
Customer ─► Meta WhatsApp Cloud API ─► POST /api/whatsapp/webhook  (this service)
                                          │  verify signature, dedupe, store
                                          │  phone → contact → conversation
                                          ▼
                                   Biz GPT  POST /api/chat/completions  (agent model "bizgpt-whatsapp")
                                          │  answer
                                          ▼
Customer ◄─ Meta WhatsApp Cloud API ◄─ send reply, store it, mirror the chat into Biz GPT
```

- Open WebUI is not modified for messaging. This service talks to it **only through its HTTP API**
  (API key), never through its database.
- The Meta access token and the Biz GPT API key live **only in this service's environment**.
  The browser and the Biz GPT tool never see them.
- Every WhatsApp conversation is also saved as a normal Biz GPT chat (title `WhatsApp · Name (+91…)`,
  tag `whatsapp`), owned by the API-key user, so staff can read it in Biz GPT.

## What's in the box

| Part | Where |
|---|---|
| FastAPI service (webhook, messaging, conversations, status) | `services/whatsapp/app/` |
| PostgreSQL schema + Alembic migrations | `app/models/`, `migrations/` |
| Biz GPT tool for staff/agents (`send_whatsapp_message`, `send_whatsapp_template`, `get_whatsapp_contact`, `get_whatsapp_conversation`, `get_whatsapp_messages`, `list_whatsapp_templates`) | `owui/tools/bizgpt_whatsapp.py` |
| Agent model that answers customers | `owui/models/bizgpt-whatsapp.json` |
| Integrations page (admin): status, phone number, business, webhook, AI agent, auto-reply, test, disconnect, stats, recent conversations | `open-webui/src/routes/(app)/integrations/`, `open-webui/src/lib/components/bizgpt/integrations/WhatsAppCard.svelte` |
| Admin proxy for that page (keeps the service key server side) | `open-webui/backend/open_webui/bizgpt/whatsapp.py` |
| Mock Meta + Biz GPT + LLM, and a signed test-webhook sender | `dev/` |

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | public | liveness + database |
| GET | `/api/whatsapp/webhook` | Meta verify token | webhook verification (`hub.challenge`) |
| POST | `/api/whatsapp/webhook` | `X-Hub-Signature-256` | messages + delivery/read status events |
| GET | `/api/whatsapp/status` | service key | WhatsApp API, Biz GPT, database, webhook configuration |
| POST | `/api/whatsapp/messages/send` | service key | free text (only within 24 h of the customer's last message) |
| POST | `/api/whatsapp/messages/template` | service key | approved template (works any time) |
| GET | `/api/whatsapp/templates` | service key | approved templates from Meta |
| GET | `/api/whatsapp/contacts/{phone}` | service key | contact |
| GET | `/api/whatsapp/conversations[?phone=]` | service key | conversations |
| GET | `/api/whatsapp/conversations/{id}` | service key | conversation + messages |
| GET | `/api/whatsapp/messages?phone=` | service key | latest messages with a contact |
| GET/PUT | `/api/whatsapp/settings` | service key | agent model, auto-reply, connected flag, stats |
| POST | `/api/whatsapp/test-connection` | service key | live Meta + Biz GPT check |

"Service key" = `Authorization: Bearer $WHATSAPP_SERVICE_API_KEY`. Interactive docs: `http://localhost:8104/docs` (host port `WHATSAPP_PORT`, default 8104; 8001 is taken by jira-mcp in nginx).

## How messages are handled

| Incoming type | What happens |
|---|---|
| text, button / list replies, template quick replies | sent to the agent, reply sent back |
| image, document | metadata stored (media id, mime type, filename, caption; no file download); the agent gets `[Customer sent image] caption` |
| location | coordinates stored; the agent gets a text description |
| audio, video, sticker, contacts, `unsupported` | stored; the customer gets the fixed `UNSUPPORTED_REPLY` |
| reaction | stored, not answered |
| status `sent` / `delivered` / `read` / `failed` | updates the outbound message (never moves backwards; errors recorded) |

Safety behaviour:

- **Duplicates:** `whatsapp_message_id` is unique in the database, so Meta redeliveries are stored once and answered once.
- **Fast 200:** the webhook stores the message and returns immediately. The AI reply runs in the background.
  Messages stored but not yet answered when the service restarts are picked up again at startup (last 15 min).
- **Biz GPT down or slow:** the customer gets `FALLBACK_REPLY`, and the error is saved on the message.
- **Meta errors:** retries on connection errors, 429 and 5xx for reads. Sends are only retried when
  the request provably never reached Meta, so a customer is never sent the same reply twice.
- **Rate limit:** at most `RATE_LIMIT_PER_MINUTE` AI replies per contact per minute. Extra messages are stored, not answered.
- **24-hour window:** free-text sends from staff are refused outside Meta's customer-service window. Use a template.
- **Disconnect** (Integrations page) or **Auto-reply off:** messages are still stored, but nobody answers automatically.
- **Logs:** JSON lines. Tokens, keys and bearer headers are redacted. Phone numbers are masked (`919******210`).
- **Conversations:** a new conversation (and a new Biz GPT chat) starts after `CONVERSATION_TIMEOUT_HOURS` of silence.
  The agent sees the last `HISTORY_MESSAGES` messages.

## Setup

### 1. Meta (once)

In [developers.facebook.com](https://developers.facebook.com) → your app → **WhatsApp**:

1. **API Setup:** note the **Phone number ID** and the **WhatsApp Business Account ID**.
2. **Business Settings → System users:** create a system user, assign the app and the WhatsApp account,
   and generate a **permanent token** with `whatsapp_business_messaging` and `whatsapp_business_management`.
   (The 24-hour test token also works for a first try.)
3. **App settings → Basic:** copy the **App secret**.
4. Choose a random **verify token**: `openssl rand -hex 16`.

### 2. Biz GPT (once)

1. Create a Biz GPT user for the service, e.g. `whatsapp-bot@…`, and make it an **admin**
   (it needs the agent model, and it owns the mirrored chats). Sign in as that user →
   **Settings → Account → API Keys** → create a key (`sk-…`).
2. Generate the shared service key: `openssl rand -hex 32`.

### 3. Configure `bizgpt/.env`

```bash
WHATSAPP_ACCESS_TOKEN=EAA…            # step 1.2
WHATSAPP_PHONE_NUMBER_ID=…            # step 1.1
WHATSAPP_BUSINESS_ACCOUNT_ID=…        # step 1.1
WHATSAPP_APP_SECRET=…                 # step 1.3
WHATSAPP_VERIFY_TOKEN=…               # step 1.4
WHATSAPP_OPENWEBUI_API_KEY=sk-…       # step 2.1
WHATSAPP_SERVICE_API_KEY=…            # step 2.2 (Biz GPT and the service share it)
WHATSAPP_DB_PASSWORD=…                # any strong password
BIZGPT_BASE_MODEL=…                   # already set; the WhatsApp agent uses the same base model
```

`.env` is git-ignored. Never commit these values.

### 4. Start

```bash
docker compose up -d --build bizgpt-whatsapp whatsapp-db
docker compose up -d --build open-webui     # rebuilds Biz GPT with the Integrations page
python3 scripts/sync.py                     # installs the bizgpt_whatsapp tool and bizgpt-whatsapp model
curl -s localhost:8104/health
```

The service runs its database migrations (`alembic upgrade head`) on every start.

### 5. Publish the webhook (HTTPS)

Meta must reach `https://<your-host>/api/whatsapp/webhook`. Publish **only that path**:

- **Server:** add `deploy/nginx-webhook.conf` to the HTTPS server block, then `sudo nginx -t && sudo systemctl reload nginx`.
- **Local development:** use a tunnel, for example
  `ngrok http 8104` or `cloudflared tunnel --url http://localhost:8104`, and use the HTTPS URL it prints.
  Anyone who has the tunnel URL can reach the service. Keep `WHATSAPP_APP_SECRET` set: unsigned
  webhook requests are then rejected, and the rest of the API still needs the service key. Stop
  the tunnel when you're done.

Then in Meta → WhatsApp → **Configuration → Webhook**:

1. Callback URL `https://<your-host>/api/whatsapp/webhook`, Verify token = `WHATSAPP_VERIFY_TOKEN` → **Verify and save**.
2. **Webhook fields → messages → Subscribe.**

### 6. Check

1. Biz GPT → Dashboard: the **WhatsApp** row appears under *Integrations Status*. Click it to open **Integrations**.
2. **Test Connection** should show WhatsApp API OK (your number and business name) and Biz GPT OK.
3. Send a WhatsApp message to the business number from your phone. You should get the agent's reply.
4. In Biz GPT, the chat `WhatsApp · <your name> (+…)` shows the conversation.
5. `curl -s -H "Authorization: Bearer $WHATSAPP_SERVICE_API_KEY" localhost:8104/api/whatsapp/status`

## Using it from Biz GPT chat (staff)

Attach the **Biz GPT WhatsApp** tool to a model (Workspace → Models → Tools), e.g. *Biz GPT Assistant*:

> Show my latest WhatsApp messages with +91 98765 43210
> Send them "Your order has shipped" on WhatsApp

Sending always shows a preview first and needs your confirmation. By default only admins can send
(tool valve `ADMIN_ONLY`). Don't attach this tool to `bizgpt-whatsapp` itself: the customer-facing
agent should not be able to message other people.

## Local development without Meta

```bash
cd services/whatsapp
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
pytest                                   # 67 tests, all external APIs mocked

# Run everything locally against mocks (SQLite, no Docker):
python dev/mock_upstream.py &            # fake Meta Graph API + fake Biz GPT on :5056
DATABASE_URL=sqlite+aiosqlite:///./dev.db WHATSAPP_GRAPH_URL=http://localhost:5056 \
OPENWEBUI_BASE_URL=http://localhost:5056 WHATSAPP_ACCESS_TOKEN=EAAdev WHATSAPP_PHONE_NUMBER_ID=555 \
OPENWEBUI_API_KEY=sk-dev WHATSAPP_SERVICE_API_KEY=dev WHATSAPP_VERIFY_TOKEN=dev WHATSAPP_APP_SECRET=dev \
uvicorn app.main:app --port 8001 &
WHATSAPP_APP_SECRET=dev python dev/send_test_webhook.py --phone-number-id 555 "Hello"
curl -s localhost:5056/_sent             # the reply the service "sent"
```

The mock also serves an OpenAI-compatible LLM (`/v1/models`, `/v1/chat/completions`, model `mock-gpt`).
Add `http://<mock>:5056/v1` as an OpenAI connection in a test Biz GPT to run the whole chain through
a real Biz GPT without a real LLM.

Standalone deployment (service + its own Postgres, without the rest of Biz GPT):
`cp .env.example .env`, fill it in, then `docker compose up -d --build` in this folder.

## Configuration reference

See `.env.example`. The main settings:

| Variable | Default | |
|---|---|---|
| `WHATSAPP_API_VERSION` | `v23.0` | Graph API version |
| `WHATSAPP_AGENT_MODEL` | `bizgpt-whatsapp` | initial agent. After that, change it on the Integrations page |
| `OPENWEBUI_MIRROR_CHATS` | `true` | save conversations as Biz GPT chats |
| `OPENWEBUI_TIMEOUT_SECONDS` | `90` | per AI answer |
| `AUTO_REPLY_ENABLED` | `true` | initial auto-reply setting |
| `HISTORY_MESSAGES` | `20` | context sent to the agent |
| `CONVERSATION_TIMEOUT_HOURS` | `24` | silence before a new conversation starts |
| `RATE_LIMIT_PER_MINUTE` | `10` | AI replies per contact per minute (`0` = off) |
| `MARK_AS_READ` | `true` | blue ticks on incoming messages |
| `UNSUPPORTED_REPLY`, `FALLBACK_REPLY` | English text | fixed replies |

Run a single uvicorn worker: the per-contact ordering lock and the rate limiter live in memory.
