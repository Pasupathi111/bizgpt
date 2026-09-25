# Dynamic Forms Reuse Analysis

Audit date: 2026-09-25.

Scope:
- `rjsf-team/react-jsonschema-form`
- `formio/react`
- `optimajet/formengine`
- `ginkgobioworks/react-json-schema-form-builder`

Goal: choose the reuse-first base for BizGPT Dynamic Forms without forking any of these projects and without coupling BizGPT to Open WebUI internals.

## 1. Decision

**Recommendation: use RJSF as the renderer foundation for BizGPT Dynamic Forms.**

Why:
- BizGPT's source of truth is **AI-generated JSON Schema + prefilled values + validation**.
- RJSF is the strongest direct match for that requirement.
- `@rjsf/shadcn` gives us the UI direction we want without inventing a renderer.
- It fits the existing BizGPT architecture: external forms service, FastAPI backend, React/TypeScript frontend, Open WebUI tool/embed integration.

**Do not use Form.io or FormEngine as the primary BizGPT renderer.**

- **Form.io** is powerful, but its center of gravity is the Form.io platform and Form.io schema model, not plain JSON Schema as the contract between AI and renderer.
- **FormEngine** is promising and shadcn-friendly, but it uses its own form JSON format. That makes it a worse fit for AI-generated JSON Schema and would add a translation layer we do not need.

**Optional future add-on:** use `react-json-schema-form-builder` only if we later need an internal admin UI for manually editing JSON Schema and `uiSchema`. It is not the runtime renderer.

## 2. BizGPT requirements

BizGPT needs this flow:

```text
User request
→ AI extracts intent
→ AI generates or updates JSON Schema
→ AI identifies known and missing fields
→ prefill known values
→ render dynamic form
→ user fills missing values
→ validate
→ confirmation
→ execute BizGPT tool or action
```

The key architectural constraint is that **JSON Schema is the AI-to-UI contract**.

That means the best renderer is the one that:
- accepts JSON Schema directly,
- works well with prefilled values,
- validates predictably on both client and server,
- lets us add BizGPT-specific wrappers without dragging in a larger platform.

## 3. Comparison summary

| Criterion | RJSF | Form.io React | FormEngine | Notes for BizGPT |
|---|---|---|---|---|
| License | Apache-2.0 | MIT | MIT | All are usable commercially |
| React / TypeScript compatibility | Excellent | Good | Good | All are React-compatible |
| shadcn/ui compatibility | **Excellent** via `@rjsf/shadcn` | Weak / custom work needed | Good | RJSF is the cleanest fit |
| JSON Schema support | **Native** | Indirect / not primary model | Partial, but uses its own form JSON | RJSF matches our contract best |
| Dynamic fields | Good | Excellent | Excellent | All support dynamic behavior |
| Conditional fields | Good via JSON Schema + dynamic UI | Excellent | Excellent | Form.io and FormEngine are stronger here, but with higher model mismatch |
| Validation | **Strong** with AJV | Strong | Strong with Zod-based engine | RJSF aligns with server-side JSON Schema validation |
| Prefill | **Native** via `formData` | Native | Native | All can prefill |
| File upload | Limited by default | **Strong** | Custom / component-dependent | RJSF needs a BizGPT custom upload widget for production |
| Custom components | Strong | Strong | Strong | All can be extended |
| Form builder support | None built-in | Strong, but builder path is platform-centric and enterprise-heavy | **Strong** | Builder is secondary for BizGPT phase 1 |
| Production maturity | **High** | High | Medium | RJSF has the broadest renderer maturity |
| Bundle size | Moderate | Heavy | Moderate | Form.io is the heaviest footprint |
| FastAPI backend integration | **Straightforward** | Possible, but platform-oriented | Straightforward | RJSF keeps backend simple |
| Open WebUI / MCP integration | **Straightforward** | Possible, but overkill | Possible | RJSF works cleanly as an external service |
| Long-term maintainability | **High** | Medium | Medium | RJSF has the least architectural drag |

## 4. Detailed comparison

### 4.1 `rjsf-team/react-jsonschema-form`

Repository: <https://github.com/rjsf-team/react-jsonschema-form>

**Strengths**
- Native JSON Schema renderer, which is exactly what BizGPT needs.
- Mature React ecosystem project with strong maintenance history.
- `@rjsf/shadcn` already exists, so we do not need to hand-map every widget to shadcn/ui.
- `@rjsf/validator-ajv8` gives us predictable client-side JSON Schema validation.
- Supports prefilled values directly through `formData`.
- Supports custom widgets, custom fields, custom templates, and dynamic `uiSchema`.
- Works cleanly inside an external React app that can be embedded into Open WebUI chat or side panel.

**Weaknesses**
- Built-in file upload support is limited to `data-url` style handling, which is not enough for enterprise-grade binary upload flows.
- No built-in visual form builder.
- Complex conditional UX sometimes needs `uiSchema` logic in addition to raw JSON Schema.

**Fit for BizGPT**
- **Best fit.**
- Lets AI generate JSON Schema directly with no translation layer.
- Keeps BizGPT-specific logic in our own service: intent extraction, missing-field detection, prefill, confirmation, submit, action execution.
- Keeps Open WebUI upgrade-safe because the form engine stays outside `open-webui/`.

### 4.2 `formio/react`

Repository: <https://github.com/formio/react>

**Strengths**
- Very capable dynamic forms platform.
- Strong conditional logic and workflow-oriented form behavior.
- First-class file components and custom component extension model.
- Strong builder story in the Form.io ecosystem.

**Weaknesses**
- The center of the architecture is the Form.io platform and Form.io form schema, not plain JSON Schema as the runtime contract.
- Embedded builder support in React is tied to broader Form.io platform capabilities and enterprise modules.
- Styling does not naturally align with shadcn/ui; we would be adapting a platform renderer, not using a native shadcn path.
- Heavier runtime and larger conceptual surface area than BizGPT needs.
- Higher risk of platform lock-in for a capability we want to keep lightweight and independent.

**Fit for BizGPT**
- Good product, wrong center of gravity.
- We would spend time translating AI-generated JSON Schema into Form.io's model or reshaping the AI contract around Form.io.
- That increases complexity and long-term maintenance for no clear advantage in the first BizGPT phase.

### 4.3 `optimajet/formengine`

Repository: <https://github.com/optimajet/formengine>

**Strengths**
- Modern React-based form engine with good documentation momentum.
- Good shadcn/ui story.
- Strong dynamic behavior, conditional rendering, custom components, and visual builder options.
- Lighter-weight than a full Form.io platform adoption.

**Weaknesses**
- Its runtime model is **FormEngine JSON**, not plain JSON Schema as the form contract.
- JSON Schema exists mainly around validating FormEngine configuration, not as the direct end-user form model we want AI to emit.
- Lower production maturity than RJSF.
- Adopting it would still require a translation layer from BizGPT JSON Schema to FormEngine JSON.

**Fit for BizGPT**
- Attractive if our product goal were "build a visual form builder platform."
- Not ideal when the main requirement is "AI produces JSON Schema, then we render and validate it immediately."
- Better as a future builder exploration than as the phase-1 renderer.

### 4.4 `ginkgobioworks/react-json-schema-form-builder`

Repository: <https://github.com/ginkgobioworks/react-json-schema-form-builder>

**Role**
- This is a **builder**, not the primary runtime renderer.

**Strengths**
- Useful for visually authoring JSON Schema and `uiSchema`.
- Natural companion to RJSF because it stays in the JSON Schema world.

**Weaknesses**
- MUI-centered, not shadcn/ui-centered.
- It does not replace the need for a runtime renderer and BizGPT execution flow.
- Not needed for the AI-first phase, because the AI is generating the schema already.

**Fit for BizGPT**
- Good optional admin tool later.
- Not the right starting point for the runtime dynamic-forms engine.

## 5. Criterion-by-criterion decision notes

### License

| Candidate | License | Verdict |
|---|---|---|
| RJSF | Apache-2.0 | Good |
| Form.io React | MIT | Good |
| FormEngine | MIT | Good |
| RJSF Builder | Apache-2.0 | Good |

No license blocker among the four candidates.

### React / TypeScript compatibility

- **RJSF:** strong TypeScript support and mature React integration.
- **Form.io React:** React library with TypeScript support, but much of the mental model comes from the wider Form.io platform.
- **FormEngine:** modern TS-first posture.
- **Builder:** React/TS friendly, but MUI-based.

### shadcn/ui compatibility

- **RJSF:** best option because `@rjsf/shadcn` already exists and is production-usable.
- **Form.io:** no first-class shadcn path.
- **FormEngine:** has shadcn support, but still not aligned with our JSON Schema contract.

### JSON Schema support

- **RJSF:** native and central.
- **Form.io:** not the primary runtime model.
- **FormEngine:** supports JSON Schema around config generation and validation, but the rendered form contract is still FormEngine JSON.

This is the deciding category. BizGPT needs **direct JSON Schema in, rendered form out**.

### Dynamic fields and conditional fields

- **Form.io** and **FormEngine** are stronger out of the box for highly visual conditional flows.
- **RJSF** is still sufficient for BizGPT because our first requirement is not a public survey builder; it is AI-generated task forms with predictable schema-driven logic.
- For BizGPT, the combination of:
  - JSON Schema `if/then/else`, `dependencies`, `oneOf` / `anyOf`,
  - dynamic `uiSchema`,
  - and BizGPT-side preprocessing
  is enough for the initial scope.

### Validation

- **RJSF + AJV** is the cleanest match because our backend already validates JSON Schema and can continue doing so.
- **Form.io** and **FormEngine** are capable, but their validation layers would become parallel systems rather than the same contract from AI to backend.

### Prefill

All three renderers support prefilled values.

RJSF is the cleanest because the AI-extracted values can be passed straight into `formData` without conversion.

### File upload

- **Form.io:** strongest built-in story.
- **RJSF:** limited by default.
- **FormEngine:** likely possible through custom components, but not as direct as Form.io.

For BizGPT this is acceptable because file upload should be implemented as a **BizGPT custom widget + FastAPI upload endpoint + object storage**, not by picking a different whole renderer.

### Custom components

All three are extensible.

RJSF is good enough for BizGPT-specific widgets such as:
- file upload,
- integration picker,
- record selector,
- confirmation summary,
- action preview.

### Form builder support

- **RJSF:** no built-in builder.
- **Form.io:** strong builder ecosystem, but platform-centric.
- **FormEngine:** strongest open builder candidate.
- **RJSF Builder:** useful companion if we need manual schema editing later.

This category is **not phase-1 critical** because BizGPT is AI-first, not human drag-and-drop-first.

### Production maturity

RJSF is the safest choice today for a renderer:
- long-lived,
- high adoption,
- broad issue history,
- stable schema-centric mental model.

Form.io is mature too, but at the cost of taking on much more platform than we need.

FormEngine looks promising, but is still the less proven choice for this specific enterprise workflow.

### Bundle size

- **RJSF:** moderate and acceptable.
- **Form.io:** heaviest.
- **FormEngine:** can be efficient, but bundle-size comparisons depend heavily on chosen component packs.

For BizGPT, bundle size matters, but **schema-contract fit and maintainability matter more**.

### FastAPI backend integration

- **RJSF:** easiest. Backend just stores schema, prefill, state, submission, and executes actions.
- **Form.io:** possible, but nudges us toward using more of the Form.io platform.
- **FormEngine:** possible, but would require a mapping layer between BizGPT JSON Schema and FormEngine JSON.

### Open WebUI / MCP integration

All three can live outside Open WebUI, but RJSF keeps the integration thinnest:
- BizGPT service creates form instance,
- Open WebUI tool returns embedded URL,
- user completes form,
- BizGPT service validates and executes action,
- agent reads status back through stable contracts.

That is exactly the upgrade-safe architecture we want.

### Long-term maintainability

RJSF wins because it minimizes special translation logic.

The more we preserve this direct contract:

```text
AI output JSON Schema
→ BizGPT stores JSON Schema
→ renderer consumes JSON Schema
→ backend validates JSON Schema
```

the easier the system is to reason about, test, and evolve.

## 6. Final choice

### Primary renderer

**Adopt RJSF (`react-jsonschema-form`) as the BizGPT runtime form renderer.**

### Runtime architecture

Keep the form engine as an independent BizGPT service/component:

```text
Open WebUI
  ↓ supported extension points only
BizGPT tool / MCP / OpenAPI layer
  ↓
BizGPT Forms service
  - JSON Schema
  - prefill
  - validation
  - confirmation
  - action execution
  ↓
BizGPT integrations / Dify / Gmail / Outlook / WhatsApp
```

### Explicit non-decisions

- **Do not fork RJSF.**
- **Do not copy Form.io into Open WebUI.**
- **Do not replace JSON Schema with Form.io schema or FormEngine JSON.**
- **Do not put BizGPT business logic inside `open-webui/`.**

## 7. BizGPT-specific layer to build around RJSF

Build only this layer:

1. Intent extraction
2. Schema generation or update
3. Known-field extraction
4. Missing-field detection
5. Prefill injection
6. RJSF render
7. Client + server validation
8. Confirmation step
9. Action execution
10. Status/result handoff back to chat / agent

## 8. Phase-1 implementation consequence

Because the reuse decision is complete, implementation should continue with:

1. keep `bizgpt/services/forms/` as the independent forms service,
2. keep RJSF as the renderer,
3. expose forms to Open WebUI through the existing BizGPT tool/embed path,
4. add BizGPT-specific features incrementally:
   - better schema generation contracts,
   - conditional forms,
   - file upload widget,
   - action adapters,
   - Dify-backed forms,
   - agentic follow-up after submit.

## 9. Current repository alignment

The current workspace already aligns with this decision:

- `bizgpt/services/forms/web/` already uses `@rjsf/shadcn`
- `bizgpt/services/forms/app/` already provides a FastAPI service
- `bizgpt/owui/tools/bizgpt_forms.py` already exposes the form flow to Open WebUI

So the right next step is **not** to swap engines. It is to finish and validate the BizGPT-specific layer around the existing RJSF-based implementation.
