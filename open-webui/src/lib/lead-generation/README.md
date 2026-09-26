# Lead Generation module

A self-contained, static Dify/n8n-style workflow builder for lead-generation
workflows, served at **`/lead-generation`**.

The page is served inside the normal Biz GPT layout, so the app's own sidebar
wraps it. The route file is `src/routes/(app)/lead-generation/+page.svelte`, and the
sidebar entry is **Dify Workflow** in `src/lib/components/layout/Sidebar.svelte`.
Everything else lives in this folder.

## What it does

- **My Workflows** has stats, a list or grid of sample workflows, an active toggle,
  duplicate and delete.
- **Templates** is a gallery of 8 lead-gen templates with graph previews. "Use template"
  clones one into a new draft.
- **Editor** (n8n-style canvas):
  - drag nodes from the palette, or click to add (the new node is chained after the selected one)
  - drag from an output handle ● onto a node to connect it; If/Else has Yes (right) and No (bottom) outputs
  - click a connection to select it, then use 🗑 or Del to remove it; Del also removes the selected node
  - pan by dragging the background, zoom with Ctrl + scroll, fit to view, click the minimap to jump
  - node config panel with editable parameters, plus Duplicate / Delete
  - Save (Ctrl+S), Publish (bumps the version), Export JSON
- **Test Run** (Ctrl+Enter) is simulated by `engine/simulate.ts`. It walks the graph from
  the trigger, scores the test lead and takes the real branch (score > 70 → CRM, otherwise
  nurture). It animates nodes and edges and streams logs, traces and per-node output. An
  empty required parameter (`url`, `to`, `prompt`, `query`) fails that node.
- **Execution History** also records your test runs. **Variables** and **Settings** are
  editable demo screens.

State is kept in `localStorage` (`bizgpt.lead-generation.v1`). **Reset demo** restores the
sample data. No backend calls are made.

## Layout

```
lead-generation/
  LeadGenerationApp.svelte   root: shell, tabs, state, toasts
  types.ts
  data/       catalog.ts (node kinds, colours) · workflows.ts (samples, templates) · samples.ts
  engine/     geometry.ts (node size, edge paths) · simulate.ts (run planner)
  components/ Canvas, WorkflowNode, NodePalette, RightPanel, WorkflowEditor, WorkflowList,
              TemplateGallery, ExecutionHistory, VariablesView, SettingsView,
              MiniGraph, JsonView, LGIcon
  styles/     lead-generation.css (every rule scoped under .lg-app)
```
