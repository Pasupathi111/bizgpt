# Dify Workflow Studio Plan

## Goal

Build a BizGPT workflow experience that feels like the sample Dify screen:

- workflow catalog in the left nav
- workflow builder canvas in the center
- node configuration panel on the right
- run/test panel at the bottom
- live execution status for each run

But keep the architecture upgrade-safe:

- Dify stays the workflow execution backend
- BizGPT owns the business registry, access rules, run history, and dashboard UI
- Open WebUI stays decoupled and talks only to stable BizGPT contracts

## What exists today

Current working pieces:

- `bizgpt/config/workflows.yaml`
  - registry for business workflows
- `bizgpt/services/api/app/main.py`
  - lists workflows
  - loads Dify info and parameters
  - runs workflows through `POST /v1/workflows/run`
  - stores local run history
- `bizgpt/services/api/web/src/App.jsx`
  - basic dashboard with workflow catalog and details
- `bizgpt/services/forms/`
  - renders JSON-schema-based forms and can trigger Dify workflow actions
- `bizgpt/owui/functions/dify_pipe.py`
  - already shows live Dify progress when Dify is used as a model

## Gap vs sample

The current dashboard is functional, but it is still an admin panel, not a workflow studio.

Missing compared to the sample:

1. visual builder canvas with nodes and edges
2. workflow detail page instead of a single catalog/detail split view
3. node configuration side panel
4. workflow run/test tray with input, output, and logs
5. live step-by-step execution tracking in the dashboard
6. version/history and publish-state presentation
7. document upload test flow for file-based workflows
8. richer result rendering for structured outputs

## Recommended architecture

### Recommended approach

Build a BizGPT-native workflow studio UI that mirrors the Dify experience, but use Dify only as the runtime and source of execution truth.

This is better than embedding the Dify console because:

- it keeps BizGPT branding and navigation consistent
- it preserves stable contracts for chat, forms, and dashboard
- it avoids depending on Dify console internals or session auth
- it fits the project rule of keeping integrations behind BizGPT services

### Important scope choice

Phase 1 should be **read-only builder + live execution**, not a full workflow editor.

That means:

- show workflow graph
- show node metadata
- run workflows live
- show run status, outputs, and logs

But do not yet support:

- drag/drop node editing
- saving graph changes back into Dify
- creating new Dify nodes from BizGPT

This gives us the sample experience faster with much lower risk.

## Target user experience

### 1. Workflow Catalog

Path:

- `/workflows`

Shows:

- list of workflows from `workflows.yaml`
- tags, status, configured state
- production/draft badge
- latest run status

### 2. Workflow Detail / Studio

Path:

- `/workflows/:workflowId`

Main layout:

- left: workflow list / quick switcher
- center: builder canvas
- right: node configuration panel
- bottom: test run panel

Tabs:

- `Builder`
- `Runs`
- `Logs`
- `Analytics`
- `Settings`

Phase 1 should fully implement:

- `Builder`
- `Runs`
- `Logs`

`Analytics` and `Settings` can start as simple placeholders backed by real metadata.

### 3. Test Run

The workflow page should allow:

- fill inputs from normalized schema
- upload a file when workflow supports file input
- execute a live run
- watch status updates
- inspect outputs and errors

### 4. Live Run Experience

During a run, users should see:

- overall run status: queued, running, succeeded, failed, stopped
- provider run id and local run id
- start/end times
- node-level progress when available
- raw logs for troubleshooting
- structured output cards for final results

## Data model plan

### Keep `workflows.yaml` as the source of truth

Add optional UI metadata so the dashboard knows how to present each workflow:

```yaml
  - id: tender_screening
    name: Tender Screening Flow
    description: Extract criteria from a tender document and score eligibility.
    tags: [procurement, tender, compliance]
    provider: dify
    ui:
      category: Operations
      status: live
      version: v1.0
      icon: file-search
      accent_color: purple
      layout_hint: document_pipeline
    dify:
      base_url_env: DIFY_BASE_URL
      api_key_env: DIFY_WORKFLOW_TENDER_SCREENING_KEY
      app_mode: workflow
      response_mode: streaming
```

### Add a normalized graph payload

Create a BizGPT API response for studio rendering:

- `GET /api/workflows/:id/studio`

Return:

- workflow metadata
- nodes
- edges
- run capabilities
- test input schema
- provider metadata

Suggested shape:

```json
{
  "workflow": {
    "id": "tender_screening",
    "name": "Tender Screening Flow",
    "status": "live",
    "version": "v1.0"
  },
  "graph": {
    "nodes": [
      {
        "id": "start",
        "type": "start",
        "title": "Start",
        "subtitle": "Document uploaded",
        "position": { "x": 80, "y": 120 },
        "inputs": [],
        "outputs": ["file"]
      }
    ],
    "edges": [
      { "source": "start", "target": "document_parser" }
    ]
  },
  "test_form": {
    "schema": {},
    "ui_schema": {}
  }
}
```

## Where graph data should come from

### Phase 1

Use BizGPT-managed graph metadata, not live Dify graph editing APIs.

Options:

1. add graph metadata into `workflows.yaml`
2. store per-workflow studio JSON under `bizgpt/config/workflow-studio/*.json`

Recommended:

- keep business workflow registry in `workflows.yaml`
- keep visual graph layout in `bizgpt/config/workflow-studio/<workflow-id>.json`

Reason:

- separates runtime config from UI layout
- easier to iterate on the canvas without overloading the registry
- avoids inventing a complex nested YAML shape too early

### Phase 2

If Dify exposes stable graph metadata we can safely use, sync it into BizGPT as a read-only import path.

## API plan

### Existing endpoints to keep

- `GET /api/workflows`
- `GET /api/workflows/:id`
- `POST /api/workflows/:id/run`
- `GET /api/workflow-runs`
- `GET /api/workflow-runs/:runId`
- `POST /api/workflow-runs/:runId/stop`

### New endpoints for the studio

#### `GET /api/workflows/:id/studio`

Returns:

- workflow metadata
- visual graph
- live capability flags
- input schema
- last runs summary

#### `GET /api/workflows/:id/runs`

Returns workflow-specific run history for the Runs tab.

#### `GET /api/workflow-runs/:runId/events`

Returns or streams normalized run events:

- run_started
- node_started
- node_completed
- node_failed
- output_ready
- run_completed

Recommended transport for Phase 1:

- Server-Sent Events

Reason:

- simple to implement in FastAPI
- enough for dashboard live updates
- lower overhead than WebSocket for this use case

#### `GET /api/workflows/:id/logs`

Returns recent normalized logs for debugging and audit.

## Live execution plan

### Core requirement

The sample is mainly about the feeling of a workflow executing live. For that, blocking execution is not enough.

We need a streamed or polled execution layer that updates the UI while the run is in progress.

### Recommended execution strategy

1. user clicks `Run workflow`
2. BizGPT API creates a local run immediately
3. BizGPT API starts the Dify workflow in streaming mode when supported
4. BizGPT translates provider updates into normalized run events
5. UI subscribes to run events and updates the canvas, logs, and result panel live
6. final output is stored in the run store

### Event normalization

BizGPT should hide Dify-specific event shapes from the frontend.

Use a normalized event contract:

```json
{
  "type": "node_started",
  "run_id": "run_abc123",
  "workflow_id": "tender_screening",
  "node_id": "extract_criteria",
  "node_name": "LLM: Extract Criteria",
  "timestamp": "2026-09-25T18:20:31Z",
  "payload": {
    "status": "running"
  }
}
```

### File upload support

For workflows like the sample, we will need file input.

Plan:

1. add file-type input support to normalized schema
2. upload file first through BizGPT forms/API
3. map uploaded asset to the Dify workflow input format
4. include file metadata in run history

This should be part of the same studio plan, but implemented after text-input runs are stable.

## Frontend implementation plan

### Tech choice

Use the existing React dashboard and extend it.

Recommended additions:

- React Router for workflow detail pages if not already present
- React Flow for builder canvas rendering
- existing fetch layer can stay simple for now

### New frontend modules

- `pages/WorkflowsPage`
- `pages/WorkflowStudioPage`
- `components/workflows/WorkflowCanvas`
- `components/workflows/NodeCard`
- `components/workflows/NodeConfigPanel`
- `components/workflows/RunPanel`
- `components/workflows/RunLogs`
- `components/workflows/RunOutput`

### Visual states to support

Nodes should show:

- idle
- running
- success
- failed
- selected

Runs panel should show:

- test input
- latest output
- raw event stream
- stop/retry actions

## Backend implementation plan

### Phase 1 backend tasks

1. add studio metadata loader
2. add workflow-specific run listing
3. extend run store for event records
4. add SSE endpoint for live events
5. add normalized event mapping from Dify responses
6. support non-blocking run lifecycle

### Store updates

Current run store is enough for final status, but not enough for live replay.

We should add:

- `workflow_run_events`
- event type
- node id
- timestamp
- payload JSON

This allows:

- live streaming
- log replay on refresh
- future analytics

## Phased delivery

### Phase 1: Studio shell + live run MVP

Deliver:

- workflow catalog page
- workflow detail page
- read-only builder canvas
- node side panel
- run panel
- live run events for text-input workflows
- run history and logs

Use demo workflows:

- `lead_qualifier`
- `company_lead_generation`

### Phase 2: File-based workflows

Deliver:

- file input in run panel
- upload handling
- document pipeline UI
- sample `tender_screening` workflow

### Phase 3: Richer operations

Deliver:

- analytics tab
- version history tab
- publish/draft status
- retry from previous inputs
- compare runs

### Phase 4: Optional editor features

Only after Phase 1-3 are stable:

- import graph from Dify
- edit limited metadata in BizGPT
- possible future save-back flow if Dify API support is stable

## First implementation slice

For the first build, I recommend this exact slice:

1. keep current API and registry
2. add one new studio page for one workflow
3. render a static read-only graph from local JSON
4. reuse existing `run_workflow` endpoint first
5. add a simple live event stream for run status and outputs
6. validate with `lead_qualifier`
7. then add `tender_screening` as the document-style sample

This gives us a visible Dify-like workflow screen quickly, while keeping the implementation realistic.

## Risks and controls

### Risk: Dify graph metadata may not be easily available

Control:

- manage graph layout in BizGPT config first

### Risk: Dify live node events may vary by execution mode

Control:

- normalize what we can
- gracefully fall back to run-level status when node-level events are unavailable

### Risk: file upload workflows add complexity early

Control:

- keep Phase 1 focused on text-input workflows

### Risk: dashboard complexity grows too fast

Control:

- build the studio as a dedicated page, not by overloading the current single-file dashboard

## Definition of done for Phase 1

We can call Phase 1 complete when:

1. `/workflows` shows the catalog cleanly
2. `/workflows/:id` opens a Dify-style studio page
3. the canvas shows nodes and edges
4. selecting a node opens configuration details
5. the run panel can execute a real workflow
6. the UI updates live during execution
7. final outputs and logs are stored and reloadable

## Recommended next step

Start with **Phase 1 MVP** and use `lead_qualifier` as the first live workflow because it already fits the current stack and does not depend on file uploads.

After that, add **`tender_screening`** as the showcase workflow that matches the sample screenshot more closely.
