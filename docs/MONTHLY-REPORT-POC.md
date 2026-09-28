# POC: AI-Assisted Monthly Report Delivery

Photo upload → vision AI analysis → Before/During/After → location, work, date, issues with confidence →
grouping → missing-photo check → AI report text → human review/edit → approve → PDF.

This project is isolated from the other Biz GPT projects: its own service, database, UI page, form type,
config and model. It changes no other project's model and not the global default model.

## Architecture

```
Biz GPT UI  /monthly-report  (MonthlyReportApp.svelte)
   │  fetch /api/v1/bizgpt/monthly-report/*   (user's Biz GPT session)
   ▼
Biz GPT backend  bizgpt/monthly_report.py     (thin pass-through, signed-in users only)
   ▼
services/monthly-report  (FastAPI, SQLite + photo files in /data)
   ├── ai.py     AI only: analyse one photo, write report narrative; strict JSON parsing + normalising
   ├── logic.py  business rules: effective values, thresholds, grouping, missing photos, confidence summary
   ├── pdf.py    final PDF (reportlab)
   └── main.py   state machine, files, routes
   │  POST /api/chat/completions  model=monthly-report-vision (user's own session token)
   ▼
Biz GPT model "Monthly Report Vision" (Workspace → Models) → base qwen2.5vl:3b (Ollama)

Chat: model "Monthly Report" (Pipe, Workspace → Functions; source services/monthly-report/chat/monthly_report_pipe.py)
   │  photos + text from the chat, your session token
   ▼
services/monthly-report  /api/interpret (AI reads the message → validated action) + the same report API
   ▼
Dynamic in-chat forms (HTML embeds): setup → photo review → report edit → approved; buttons post back into the chat
```

Report states: `draft → processing → analyzed → in_review ⇄ rejected → approved`.
Approve is blocked until the report is generated and no photo still needs review.

| AI (model) | Application (code) |
|---|---|
| Understand and classify each image | File handling, EXIF date/time |
| Extract location/work/date/issues + confidence | Clamp answers to the project's allowed zones/work types (anything else → Unknown) |
| Write narrative sections from verified facts | Thresholds, review flags, grouping, missing-photo validation |
| | Approval state, report state, PDF |

## Model

Source `owui/models/monthly-report-vision.json` (base model from `MONTHLY_REPORT_BASE_MODEL`, e.g. `gpt-4o-mini`):

- Name **Monthly Report Vision**, ID `monthly-report-vision`, temperature 0, hidden from the chat model picker
  (`meta.hidden`): only the service calls it; users chat with the **Monthly Report** pipe
- Capabilities: Vision + File Upload on; web search, code interpreter, image generation, memory, builtin tools off
- Tool: **Biz GPT Dynamic Forms** (opens the `monthly_report_request` form in chat)
- The service calls it by ID; change with `MONTHLY_REPORT_MODEL`. To use a stronger vision model, edit the
  base model of this Workspace model (e.g. `gpt-4o`), nothing else changes.

## In the chat (no page needed)

1. New chat → pick **Monthly Report** → attach site photos → e.g. *"September 2026 report for Taman Park"*.
   If the project/month is not in the message, a **setup form** appears in the chat.
2. Live status while each photo is analysed, then a **photo review form**: thumbnail, AI values with confidence,
   dropdowns to correct, Checked / Exclude, grouping and the missing-photo check.
3. **Save & generate monthly report** → **report form** in the chat: editable sections, photos by stage/zone,
   missing information, confidence summary, **Save draft / Reject / Approve**.
4. Typed messages work too: *"IMG_0103 is during"*, *"change the remarks to: …"*, *"write the report"*,
   *"approve the report"*. Approve/Reject only happen when you actually say approve/reject.
5. After approval: the full report screen with **View report / Download PDF / Generate again / Delete & start fresh**.
6. Natural requests work in any new chat: *"Generate the October month report"* syncs Gmail (🔄 loader), imports that
   month's photo email and continues; if the month's report exists it opens at its current step (review, report,
   or approved). Emails always keep the project/month they state themselves.
7. **Approve** is always available in review; if photos are still flagged it asks to confirm them first
   (`POST /approve {"confirm_flagged": true}`; each confirmation is logged).
8. **Same result every time:** photo analyses are cached by image content + prompt + model, report text by its facts
   (`ai_cache` table). Generate can be clicked any number of times, also after approval.
9. **Delete & start fresh** (`DELETE /api/reports/{id}`): removes the report, photos, PDF and month folder, and re-arms
   its Gmail email so the month can be run again from zero.

**Photo library:** on approval the approved photos, the PDF and `photos.json` are filed in
`/data/library/<project>/<YYYY-MM>/` (Monthly Report page → 📁 Photo library; API `/api/library/...`).

**Gmail intake needs** the Google Workspace MCP server at tool tier `extended` (for `get_gmail_attachment_content`).
Bounce / auto-reply emails are ignored; an email whose photos all fail to download stays `failed` and is retried.

The pipe also answers Biz GPT background tasks (chat title) itself, so they never touch reports.

## Configuration

`config/monthly-report/projects.json`: projects, their zones, allowed work types, required stages,
review threshold (default 75%, override with `MONTHLY_REPORT_CONFIDENCE_THRESHOLD`).

## Run

```bash
docker compose up -d --build bizgpt-monthly-report open-webui   # service on 127.0.0.1:8106
```

Local development without rebuilding Biz GPT:

```bash
cd services/monthly-report && OPENWEBUI_BASE_URL=http://localhost:3000 MONTHLY_REPORT_DATA_DIR=./.data uvicorn app.main:app --port 8106
cd open-webui && WEBUI_BACKEND_URL=http://localhost:3000 npx vite dev --port 5173   # vite proxies the service
```

## Test

```bash
cd services/monthly-report && python -m pytest -q tests      # 14 tests, fake model
python3 dev/make_sample_photos.py sample-photos              # 16 demo photos (Zone B has no "During")
```

Demo: Monthly Report → project *Taman Park Landscape Maintenance*, month → drop the 16 photos → Process Photos →
review flagged cards (Edit / Confirm / Exclude) → Grouping & Validation shows *Zone B: During photo missing* →
Generate Monthly Report → edit text → Reject (optional) → Save Draft → Approve → View Report / Download PDF.

## Known limitations

- `qwen2.5vl:3b` runs locally (~15–20 s per photo on a 16 GB Mac); its confidences are not calibrated and it often
  leaves work type Unknown, so the reviewer corrects more. A stronger vision model improves this without code changes.
- Location is only taken from visible signs/stamps (by design, no guessing); GPS EXIF is not used yet.
- One processing task per report in memory; a service restart marks the run interrupted (re-run Process Photos).
- The model is private to the admin who created it in Workspace; grant access for other coordinators.
- The form webhook has no shared secret (the service port is bound to 127.0.0.1 / internal network only).
- Chat cards embed small thumbnails (~60–120 KB per card) in the chat history.
- In-chat form buttons may ask "Confirm Prompt from Embed" depending on the iframe sandbox setting.

## Production later

Stronger/cloud vision model, GPS + EXIF location matching, object storage for photos, per-project RBAC and
approver roles, audit trail export, queue/worker for large batches, PDPA retention and face/plate blurring,
report templates per client, WhatsApp/FIMS/portal delivery.
