# AI Lead Generation & Outreach POC (customer: Automobile Group)

Separate from the Monthly Report POC: its own workspace model, its own tool, its own SQLite file. Nothing of Monthly Report is used or changed.

## Pieces

| Piece | Where | Notes |
|---|---|---|
| Model `automobile-lead-outreach` ("Automobile Lead Outreach") | Workspace → Models; source `owui/models/automobile-lead-outreach.json` | base `qwen2.5:7b`, native function calling, temp 0.1, only tool `automobile_lead_outreach`, builtin tools off |
| Tool `automobile_lead_outreach` | Workspace → Tools; source `owui/tools/automobile_lead_outreach.py` | all UI (in-chat embeds), validation, template engine, storage, POC email guard |
| AI model for generation | tool valve `AI_MODEL` (default `qwen2.5:7b`) | called through Biz GPT `/api/chat/completions` with a JSON schema |
| Storage | `/app/backend/data/automobile_lead_outreach/poc.db` (Biz GPT data volume) | tables: customers, leads, email_templates, emails |
| Email | existing `bizgpt-integrations` (Gmail via Nango), new `POST /api/emails/send` | integrations key read from the server env, never in the browser |

## Flow (all inside the chat)

Customer profile card → Generate leads (AI JSON → validation → SAMPLE leads) → Lead list (filters: industry, relevance, status, search) → Lead details form (rendered from `LEAD_FIELDS`) → Save (validated server-side) → Generate Email (template + one AI sentence) → Preview (edit / save) → Send Test Email → result card.

Embed buttons post a chat message (e.g. `Send test email E-0002`); the model maps it to the tool call. Nothing is sent unless a person clicks Send.

## POC email safety

- `POC_RECIPIENT = 'prsap94@gmail.com'` is a code constant. `send_test_email` has no recipient parameter, so neither the model nor the UI can change where mail goes.
- The lead's address is stored as `intended_recipient`; `actual_recipient` is always the POC inbox; `environment=POC`.
- Sent mail gets a `[TEST]` subject prefix and a banner naming the original intended recipient.
- An email id can be sent once (`already_sent` afterwards); only DRAFT emails can be edited.

## Real companies (Singapore + Malaysia)

"Generate leads" now finds **real companies**. The old fictional leads (`verification_status = SAMPLE`) are hidden everywhere but kept in the database.

1. **Web search:** DuckDuckGo, via the `ddgs` library that ships with Biz GPT (no API key). It runs 2 queries per industry per market from `SEARCH_QUERIES`, about 24 results in total. Directories, job sites, social media, news, marketplaces and gov/edu sites are skipped (`BLOCKED_DOMAINS`), and so are companies already in the list.
2. **AI selection:** the AI only picks result numbers. The code then keeps a pick only if:
   - the company name appears in that result;
   - the website is the company's own, meaning the name is in the domain or the result is the homepage;
   - the country comes from the `.my` / `.sg` domain ending or is one of the markets.

   Picks are rotated across industry × country.
3. **Company website:** the code reads the homepage and contact page, with no AI involved:
   - general email: same domain only;
   - phone: must match the market (+65 for Singapore, +60 or a local number for Malaysia);
   - address.

   Pages behind a bot check are ignored. A domain-looking name is replaced by the name in the site's own title; if that can't be read, the lead is dropped.
4. **AI assessment:** why this company, highlights and a next step, based only on the website text. Any number or revenue claim that isn't in that text is removed. Revenue shows "Not publicly disclosed" unless a person enters a published figure.

Leads are badged **REAL COMPANY · WEB SOURCED** and show their Source pages. A person should review each one and set Verification to **VERIFIED**. Web search can surface dubious sites, e.g. a "gold mining company in Singapore". Contacts are always the company's general enquiries, never scraped personal names.

## AI recommendation per lead

Every lead gets an **AI Recommendation** block automatically:

- New leads get it when they are generated.
- When the lead list or a lead form is opened, any lead without one is filled first. This runs in batches of 4 leads per model call; if a batch drops a lead, that lead is retried on its own.
- The "Get AI recommendation" button appears only if the AI call fails.
- `recommend_lead` refreshes a single lead's recommendation: use the "AI Recommendation" button in the lead form, or type "Get AI recommendation for lead L-xxxx".

The block contains `why_recommended`, up to 4 highlights taken from the company's website, and `recommended_action` for the target role. The lead list shows "⭐ AI top picks" and can be sorted by AI relevance, revenue (when published) or newest.

## Update the live tool/model from the repo

The tool and model were created in the Workspace UI. To push the source again, use Workspace → Tools → Automobile Lead Outreach → paste the file. You can also use the API (`POST /api/v1/tools/id/automobile_lead_outreach/update`). Do not run `scripts/sync.py` just for this, because it re-syncs every project.

## Tests

`docker cp owui/tools/automobile_lead_outreach.py bizgpt-webui:/tmp/slo.py && docker cp tests/test_automobile_lead_outreach.py bizgpt-webui:/tmp/t.py && docker exec bizgpt-webui python3 /tmp/t.py /tmp/slo.py`
