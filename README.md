# BizGPT – add-on layer for Biz GPT

Everything BizGPT-specific lives here. **`../open-webui/` is never edited.** Biz GPT runs from the
official Docker image, and our code is pushed into it through its API.

```
bizgpt/
├── docker-compose.yml        Biz GPT (official image, version pinned in .env)
├── .env.example              copy to .env and fill in
├── owui/functions/           code loaded into Biz GPT (dify_pipe.py = Dify connector)
├── owui/tools/               tools for the LLM (dynamic forms, WhatsApp… later)
├── scripts/sync.py           pushes owui/* into Biz GPT and sets valves from .env
├── demo/dify/                importable Dify demo app + sample knowledge doc
└── dev/mock_dify.py          fake Dify API for testing without the real server
```

## Upgrading Biz GPT

1. In `.env`, change `OWUI_VERSION=v0.11.4` to the new tag.
2. `docker compose pull && docker compose up -d`
3. `python3 scripts/sync.py`

Chats, users and settings live in the `bizgpt-webui-data` volume, so they survive the upgrade.

## First-time setup

```bash
cp .env.example .env              # fill in DIFY_BASE_URL + DIFY_APPS
docker compose up -d              # open http://localhost:3000, create the admin account
# Profile → Settings → Account → API Keys → create key → paste into .env as OWUI_API_KEY
python3 scripts/sync.py           # installs + enables the Dify connector
```

Each Dify app now appears in the model picker as **Dify / <name>**.

See [DEMO.md](DEMO.md) for the client showcase script.
