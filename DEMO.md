# Client showcase: Dify inside BizGPT

## Two ways Dify connects

| | A. Dify app as a model (built: `owui/functions/dify_pipe.py`) | B. Dify app as a tool (zero code) |
|---|---|---|
| What the client sees | Pick **Dify / Lead Qualifier** in the model picker and chat with it | A normal model (GPT or Claude) decides when to call the Dify workflow |
| Live feedback | Each Dify node shows as a live status line; knowledge sources appear as citations | The tool call appears in the chat |
| Setup | Add the app to `DIFY_APPS` in `.env`, then run `scripts/sync.py` | Dify: app → **Publish → MCP server** → copy the URL. Biz GPT: Admin → Settings → External Tools → **+** → type MCP (Streamable HTTP) → paste the URL |
| Needs | Any Dify version (uses the standard `/v1` API) | A Dify version with "publish as MCP server" (1.6+) |

## Prepare the Dify apps (once, on your Dify server)

1. **Lead Qualifier (workflow):** Dify → Studio → *Import DSL file* → `demo/dify/lead-qualifier.yml`.
   In the two LLM nodes, select a model you have configured. Publish, then go to **API Access** → create an API key.
2. **HR Policy Assistant (chatflow + knowledge):** Knowledge → create a dataset → upload `demo/dify/sample-hr-policy.md`.
   Studio → Create → Chatflow → add a *Knowledge Retrieval* node that uses the dataset → publish → create an API key.
   Turn on **Citations** in the app features so sources reach BizGPT.
3. Put both keys into `DIFY_APPS` in `.env`, then run `python3 scripts/sync.py`.

## Demo script (about 5 minutes)

**Scene 1: business workflow.** Model: *Dify / Lead Qualifier*. Paste:

> Hi, I'm Priya from Nexora Logistics. We're a 120-person freight company and want an AI assistant for our
> customer-support team. Budget is approved for this quarter and we'd like to go live within 6 weeks.
> Can we set up a call?

Point out: every Dify step (Extract → Score → Draft reply) shows live, and the result is a scored lead with a ready-to-send reply.
Then paste a weak lead ("Just browsing, student project, no budget") to show it becomes Cold with a different reply.

**Scene 2: company knowledge with sources.** Model: *Dify / HR Policy Assistant*.
Ask *"How many leave days can I carry forward and when do they expire?"*, then the follow-up
*"And what about sick leave?"* (the conversation continues in Dify). Click the citation to show the source document.

**Scene 3: the combined flow (option B + your Gmail MCP).** Use a GPT/Claude model with the Gmail MCP and the Lead Qualifier MCP tool enabled:

> Read my latest email from a prospect, qualify it with the Lead Qualifier, and draft the reply in Gmail.

## Offline rehearsal (no Dify server needed)

`python3 dev/mock_dify.py`, then set `DIFY_BASE_URL=http://host.docker.internal:5055` (any api_key works).
The mock returns canned answers with the same live steps and citations.
