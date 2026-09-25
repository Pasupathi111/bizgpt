# Dify Workflow Plan

## 1. Goal

Use the existing self-hosted Dify instance as BizGPT's workflow engine without embedding Dify into Open WebUI and without coupling the agent to Dify-specific app details.

BizGPT should expose a stable workflow layer:

- `get_workflows`
- `get_workflow`
- `run_workflow`
- `get_workflow_run`
- `stop_workflow_run`

The agent calls those contracts. BizGPT then routes the request to the correct Dify workflow app and API key.

## 2. What already exists

The current repo already has the main pieces we need:

- `owui/functions/dify_pipe.py`
  - exposes Dify apps as Open WebUI models
  - good for "Dify app as model" demos
- `services/forms/app/actions.py`
  - already supports `action.type == "dify_workflow"`
  - already calls `POST /v1/workflows/run`
- `services/forms/app/registry.py`
  - already carries Dify env references in form action definitions
- `docs/INTEGRATION-CATALOG.md`
  - already defines the stable workflow contracts
- `dev/mock_dify.py`
  - already gives us a testable fake Dify API

So this phase is mostly about standardizing and hardening the Dify path, not inventing it from scratch.

## 3. Target architecture

```text
User
  -> Open WebUI BizGPT Assistant
  -> BizGPT stable workflow contracts
  -> bizgpt-mcp / workflow provider
  -> Dify Service API
  -> Dify workflow app
```

Two Dify integration modes should remain supported:

1. Primary: Dify as a workflow backend
   - used by `run_workflow`
   - used by Dynamic Forms submit actions
   - stable and upgrade-safe for the agent layer

2. Secondary: Dify as a model
   - keep `dify_pipe.py`
   - useful for direct Dify demos and specialist assistants
   - not the main BizGPT contract path

## 4. Design principles

1. Do not depend on Dify console internals.
2. Do not let the LLM call raw Dify app IDs or raw Dify endpoints.
3. Keep Dify API keys out of prompts, chat state, and repo-tracked config.
4. Make workflows discoverable through a BizGPT registry because Dify service keys are per app and do not offer a global "list workflows" API.
5. Use `GET /v1/parameters` as the source for workflow input schema so Dynamic Forms can reuse it.
6. Support both direct tool execution and form-mediated execution.

## 5. Proposed registry

Add a repo-tracked registry file:

`bizgpt/config/workflows.yaml`

Each entry should describe one business-facing workflow.

Example shape:

```yaml
version: 1
workflows:
  - id: leave_request
    name: Leave Request
    description: Submit annual leave for manager review.
    tags: [hr, approval]
    provider: dify
    dify:
      base_url_env: DIFY_BASE_URL
      api_key_env: DIFY_WORKFLOW_LEAVE_REQUEST_KEY
      app_mode: workflow
      response_mode: blocking
    input:
      source: dify_parameters
    execution:
      requires_confirmation: true
      expose_as_form: true
      expose_as_tool: true
    access:
      allowed_groups: [employees, managers]

  - id: it_support_ticket
    name: IT Support Ticket
    description: Create and triage an internal IT support request.
    tags: [it, support]
    provider: dify
    dify:
      base_url_env: DIFY_BASE_URL
      api_key_env: DIFY_WORKFLOW_IT_SUPPORT_KEY
      app_mode: workflow
      response_mode: blocking
    input:
      source: dify_parameters
    execution:
      requires_confirmation: true
      expose_as_form: true
      expose_as_tool: true
    access:
      allowed_groups: [employees]
```

Why this registry is needed:

- Dify service API keys are app-specific
- BizGPT needs a business-friendly workflow catalog
- access control should stay in BizGPT
- metadata such as tags, confirmation requirements, and form exposure belong here

## 6. Provider contract behavior

### `get_workflows`

Returns registry entries the current user is allowed to see.

Each result should include:

- `id`
- `name`
- `description`
- `tags`
- `input_mode`
- `requires_confirmation`
- `supports_form`

### `get_workflow`

For a given workflow:

1. load registry entry
2. call Dify `GET /v1/info`
3. call Dify `GET /v1/parameters`
4. convert Dify parameters into BizGPT input schema
5. return normalized metadata

Normalized return should include:

- workflow identity and description
- Dify app metadata
- normalized JSON Schema
- UI hints for forms
- required fields
- example inputs if defined in registry

### `run_workflow`

Flow:

1. validate workflow exists and user is allowed
2. validate or coerce inputs against normalized schema
3. if `requires_confirmation` and `confirm != true`, return preview
4. call `POST /v1/workflows/run`
5. store run metadata in BizGPT for polling/audit
6. return normalized result

Normalized result should include:

- `run_id`
- `status`
- `outputs`
- `elapsed_time`
- `reference`
- `provider_run_id`

### `get_workflow_run`

Uses the stored mapping plus Dify `GET /v1/workflows/run/{id}`.

Return:

- `run_id`
- `status`
- `outputs`
- `error`
- `started_at`
- `finished_at`
- `provider_run_id`

### `stop_workflow_run`

Uses Dify task stop endpoint and returns a normalized status object.

## 7. Parameter-to-form mapping

This is the most important bridge between Dify and Dynamic Forms.

Target rule:

`Dify workflow parameters -> normalized JSON Schema -> RJSF form`

Mapping strategy:

1. Fetch `GET /v1/parameters`
2. Convert Dify field types to JSON Schema
3. Preserve labels, descriptions, defaults, enums, and required fields
4. Attach BizGPT `uiSchema` hints where useful
5. Prefill any values extracted by the agent
6. Let forms service validate again before execution

Example mapping:

| Dify parameter | JSON Schema | Notes |
|---|---|---|
| text input | `type: string` | add title/description |
| paragraph | `type: string` | `ui:widget: textarea` |
| number | `type: number` or `integer` | preserve min/max if present |
| select | `enum: [...]` | use select widget |
| boolean | `type: boolean` | checkbox or switch |
| date/time | `type: string`, `format: date` or `date-time` | agent can prefill relative dates |
| file | custom handling | phase 2, after core text/number/select flow |

Important constraint:

The forms service should remain the final validator, even when the workflow is invoked directly from chat.

## 8. Execution modes

We should support three execution modes.

### A. Direct tool run

Best for short workflows with only a few inputs already present in the prompt.

Example:

```text
User: Run the lead qualifier for Acme. They have 80 employees, budget approved, timeline 30 days.
Agent: get_workflow -> run_workflow
```

### B. Tool plus generated form

Best when the user intent is clear but required inputs are missing.

Example:

```text
User: I need to apply for leave next month.
Agent: get_workflow(leave_request) -> create form from Dify parameters -> prefill known dates -> user fills remaining fields -> submit -> run_workflow
```

### C. Predefined business form action

Best when the workflow is packaged as a formal business process in `config/forms/*.json`.

Example:

```json
{
  "id": "leave_request",
  "title": "Leave Request",
  "action": {
    "type": "dify_workflow",
    "reference_prefix": "LVR",
    "dify_base_url_env": "DIFY_BASE_URL",
    "dify_api_key_env": "DIFY_WORKFLOW_LEAVE_REQUEST_KEY"
  }
}
```

This is already close to what the forms service supports today.

## 9. Recommended first workflows

Start with workflows that are form-friendly, business-visible, and easy to verify.

### 1. Leave Request

Purpose:
- employee submits leave request
- Dify validates policy inputs
- routes for approval or produces a structured result

Expected inputs:
- employee_name
- leave_type
- start_date
- end_date
- reason
- handover_notes

Expected outputs:
- request status
- summary
- policy notes
- approval reference

Why first:
- ideal fit for forms
- clear required fields
- easy human verification

### 2. IT Support Ticket

Purpose:
- capture issue details
- classify severity/category
- produce ticket summary and suggested routing

Expected inputs:
- requester_name
- department
- issue_type
- severity
- device
- problem_description

Expected outputs:
- category
- priority
- support summary
- ticket payload or next action

Why first:
- good internal operations workflow
- useful for chat + form handoff

### 3. Lead Qualifier

Purpose:
- evaluate inbound sales lead
- score hot/warm/cold
- generate follow-up recommendation

Expected inputs:
- company_name
- contact_name
- employee_count
- use_case
- budget_status
- timeline

Expected outputs:
- lead_score
- qualification
- reasoning
- draft reply

Why first:
- already aligns with the repo demo assets
- great for showcasing Dify value in BizGPT

### 4. Purchase Request

Purpose:
- gather internal purchase approval details
- summarize business justification
- classify approval path

Expected inputs:
- requester
- department
- item_name
- vendor
- amount
- urgency
- justification

Expected outputs:
- approval level
- summary
- finance notes
- request reference

Why next:
- another strong form-based workflow
- pairs well with approval-style business processes

## 10. Example end-to-end flows

### Example A: leave request with form

```text
User: I need leave from Oct 14 to Oct 18 for a family trip.
Agent:
  1. get_workflows(tag=hr)
  2. get_workflow(leave_request)
  3. create form using Dify parameters
  4. prefill start_date and end_date
  5. user fills leave_type and handover_notes
  6. submit form
  7. forms service runs Dify workflow
  8. BizGPT returns approval reference and summary
```

### Example B: IT support directly from chat

```text
User: My laptop keeps restarting after the latest update. I am in finance and this blocks payroll work.
Agent:
  1. get_workflow(it_support_ticket)
  2. detect enough inputs for direct run
  3. ask for missing severity or device only if needed, otherwise use form
  4. run_workflow
  5. return priority, category, and support summary
```

### Example C: lead qualifier as tool

```text
User: Qualify this lead: 120-person logistics company, budget approved this quarter, wants rollout in 6 weeks.
Agent:
  1. run_workflow(lead_qualifier, inputs)
  2. return lead score, qualification, and draft response
```

## 11. Implementation sequence

### Phase 3A: registry and provider

Build in `services/mcp-gateway`:

- workflow provider interface
- Dify provider implementation
- registry loader for `config/workflows.yaml`
- schema normalization from `/v1/parameters`

### Phase 3B: persistence and audit

Add:

- workflow run store
- normalized run status
- request/response audit metadata
- error mapping

### Phase 3C: forms integration

Connect normalized workflow schema to:

- `get_form_types`
- `create_form`
- `submit_form`

So a Dify workflow can appear either:

- as a standalone workflow tool
- or as an auto-generated form

### Phase 3D: assistant behavior

Update BizGPT assistant guidance so it:

- prefers workflow tools for workflowable requests
- uses a form when required fields are missing
- confirms before write/approval actions

### Phase 3E: dashboard visibility

Later surface workflow catalog and workflow runs in the dashboard:

- available workflows
- recent runs
- status and errors
- average completion time

## 12. Environment variables

Recommended env additions:

```env
DIFY_BASE_URL=https://dify.yourcompany.com

DIFY_WORKFLOW_LEAVE_REQUEST_KEY=app-xxxx
DIFY_WORKFLOW_IT_SUPPORT_KEY=app-yyyy
DIFY_WORKFLOW_LEAD_QUALIFIER_KEY=app-zzzz
DIFY_WORKFLOW_PURCHASE_REQUEST_KEY=app-aaaa
```

Keep workflow keys separate instead of one shared key so:

- app boundaries stay explicit
- rotation is simpler
- accidental cross-workflow access is reduced

## 13. Error handling rules

Normalize Dify errors into BizGPT-friendly actions:

| Condition | BizGPT error action |
|---|---|
| missing connection/config | `fix_input` |
| Dify 401/403 | `fix_input` with admin-facing configuration note |
| Dify validation/input mismatch | `fix_input` |
| Dify timeout | `retry` |
| Dify run failed | `retry` or show structured failure |
| unauthorized workflow access | `fix_input` |

Do not expose raw Dify error bodies directly to end users.

## 14. Testing plan

### Unit

- registry parsing
- Dify parameter normalization
- confirmation gating
- result normalization

### Integration

Use `dev/mock_dify.py` for:

- `get_workflow`
- `run_workflow`
- `get_workflow_run`
- forms submit -> Dify action path

### End-to-end

Verify in Open WebUI:

1. direct workflow tool execution
2. workflow converted into a form
3. completed result shown back in chat
4. failed workflow returns a usable error

## 15. Immediate deliverables

The next concrete implementation items should be:

1. create `bizgpt/config/workflows.yaml`
2. add workflow provider skeleton in `services/mcp-gateway`
3. add Dify parameter -> JSON Schema normalizer
4. wire auto-generated Dify workflows into the forms registry
5. ship the first three workflows:
   - `leave_request`
   - `it_support_ticket`
   - `lead_qualifier`

## 16. Recommended decision

Proceed with Dify as the workflow backend behind BizGPT stable contracts, with Dynamic Forms as the default UI for incomplete inputs.

That gives us:

- upgrade-safe Open WebUI integration
- reuse of your existing self-hosted Dify
- clean separation between business workflows and agent behavior
- a direct path from chat -> form -> workflow -> result
