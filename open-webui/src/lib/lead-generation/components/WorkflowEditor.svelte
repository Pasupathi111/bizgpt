<script lang="ts">
	import { createEventDispatcher, onDestroy, onMount, tick } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import Canvas from './Canvas.svelte';
	import NodePalette from './NodePalette.svelte';
	import RightPanel from './RightPanel.svelte';
	import { typeOf } from '../data/catalog';
	import { clone, defaultConfig } from '../data/workflows';
	import { TEST_INPUTS } from '../data/samples';
	import { NODE_W } from '../engine/geometry';
	import { planRun } from '../engine/simulate';
	import type { EdgeStatus, LogLine, NodeStatus, RunRecord, RunStatus, RunStep, Workflow } from '../types';

	export let workflow: Workflow;

	const dispatch = createEventDispatcher<{
		back: void;
		toast: { message: string; kind?: 'success' | 'error' | 'info' };
		ran: RunRecord;
		change: void;
	}>();

	let canvas: Canvas;
	let selectedNodeId: string | null = null;
	let selectedEdgeId: string | null = null;
	let panelTab: 'run' | 'config' | 'output' = 'run';
	let panelOpen = true;
	let dirty = false;
	let savedAt = workflow.updated;
	let editingName = false;
	let publishMenu = false;
	let moreMenu = false;

	// run state
	let runStatus: RunStatus = 'idle';
	let nodeStatus: Record<string, NodeStatus> = {};
	let edgeStatus: Record<string, EdgeStatus> = {};
	let nodeMs: Record<string, number> = {};
	let nodeOutputs: Record<string, Record<string, any>> = {};
	let steps: RunStep[] = [];
	let logs: LogLine[] = [];
	let finalOutput: Record<string, any> | null = null;
	let elapsedMs = 0;
	let inputPreset = 'Form Data';
	let inputText = TEST_INPUTS['Form Data'];
	let inputError = '';
	let runToken = 0;

	const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
	const clock = () => {
		const d = new Date();
		return `${d.toTimeString().slice(0, 8)}.${String(d.getMilliseconds()).padStart(3, '0')}`;
	};
	const log = (level: LogLine['level'], message: string, node?: string) => (logs = [...logs, { time: clock(), level, message, node }]);
	const titleOf = (id: string) => workflow.nodes.find((n) => n.id === id)?.title ?? id;

	function markDirty() {
		dirty = true;
		workflow = workflow;
		dispatch('change');
	}

	function resetRun() {
		nodeStatus = {};
		edgeStatus = {};
		nodeMs = {};
		nodeOutputs = {};
		steps = [];
		logs = [];
		finalOutput = null;
		elapsedMs = 0;
	}

	async function run() {
		if (runStatus === 'running') return;
		panelOpen = true;
		panelTab = 'run';
		let input: Record<string, any>;
		try {
			input = JSON.parse(inputText);
			inputError = '';
		} catch (err) {
			inputError = `Invalid JSON: ${(err as Error).message}`;
			runStatus = 'failed';
			dispatch('toast', { message: 'Test input is not valid JSON', kind: 'error' });
			return;
		}
		if (!workflow.nodes.length) {
			dispatch('toast', { message: 'Add a trigger node before running', kind: 'error' });
			return;
		}

		resetRun();
		const token = ++runToken;
		const runId = `run_${Math.random().toString(16).slice(2, 8)}`;
		runStatus = 'running';
		const plan = planRun(workflow, input);
		log('info', `Run ${runId} started · trigger: ${workflow.trigger} · ${plan.steps.length} steps planned`);

		for (const step of plan.steps) {
			if (token !== runToken) return;
			const node = workflow.nodes.find((n) => n.id === step.nodeId);
			if (!node) continue;
			for (const id of step.via) edgeStatus[id] = 'active';
			nodeStatus[step.nodeId] = 'running';
			nodeStatus = nodeStatus;
			edgeStatus = edgeStatus;
			log('info', `Executing ${typeOf(node.kind).label}…`, node.title);

			await sleep(Math.min(1100, Math.max(380, step.ms * 0.28)));
			if (token !== runToken) return;

			const missing = ['url', 'to', 'prompt', 'query'].find((k) => k in node.config && !String(node.config[k]).trim());
			if (missing) {
				nodeStatus[step.nodeId] = 'error';
				nodeStatus = nodeStatus;
				log('error', `Parameter "${missing}" is required`, node.title);
				log('error', `Run ${runId} failed after ${steps.length + 1} steps`);
				runStatus = 'failed';
				panelTab = 'run';
				dispatch('toast', { message: `“${node.title}” failed: ${missing} is required`, kind: 'error' });
				record(runId, 'failed', input, null);
				return;
			}

			for (const id of step.via) edgeStatus[id] = 'done';
			nodeStatus[step.nodeId] = 'success';
			nodeMs[step.nodeId] = step.ms;
			nodeOutputs[step.nodeId] = step.output;
			nodeStatus = nodeStatus;
			edgeStatus = edgeStatus;
			nodeMs = nodeMs;
			nodeOutputs = nodeOutputs;
			steps = [...steps, step];
			elapsedMs += step.ms;
			log('success', `${step.log} (${step.ms < 1000 ? `${step.ms} ms` : `${(step.ms / 1000).toFixed(1)}s`})`, node.title);
		}

		for (const id of plan.skippedNodes) nodeStatus[id] = 'skipped';
		for (const id of plan.skippedEdges) edgeStatus[id] = 'skipped';
		nodeStatus = nodeStatus;
		edgeStatus = edgeStatus;
		if (plan.skippedNodes.length) log('warn', `Skipped ${plan.skippedNodes.length} node(s) on untaken branches: ${plan.skippedNodes.map(titleOf).join(', ')}`);

		finalOutput = plan.output;
		runStatus = 'success';
		log('success', `Run ${runId} succeeded in ${(elapsedMs / 1000).toFixed(1)}s · lead score ${plan.output.lead_score}`);
		dispatch('toast', { message: `Run succeeded · lead score ${plan.output.lead_score} (${plan.output.qualification})`, kind: 'success' });
		record(runId, 'success', input, plan.output.lead_score);
	}

	function record(id: string, status: 'success' | 'failed', input: Record<string, any>, score: number | null) {
		const who = input.name || (typeof input.from === 'string' ? input.from.split('<')[0].trim() : '') || 'Test lead';
		const time = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
		dispatch('ran', {
			id,
			workflowId: workflow.id,
			workflowName: workflow.name,
			status,
			trigger: 'Test run',
			durationMs: elapsedMs,
			startedAt: `Today, ${time}`,
			lead: input.company ? `${who} · ${input.company}` : who,
			score,
			nodes: steps.length
		});
	}

	function stop() {
		runToken++;
		for (const [id, s] of Object.entries(nodeStatus)) if (s === 'running') nodeStatus[id] = 'idle';
		for (const [id, s] of Object.entries(edgeStatus)) if (s === 'active') edgeStatus[id] = 'idle';
		nodeStatus = nodeStatus;
		edgeStatus = edgeStatus;
		runStatus = 'failed';
		log('warn', 'Run cancelled by user');
	}

	function addNode(kind: string, pos?: { x: number; y: number }) {
		const t = typeOf(kind);
		const anchor = !pos && selectedNodeId ? workflow.nodes.find((n) => n.id === selectedNodeId) : null;
		const at = pos ?? (anchor ? { x: anchor.x + NODE_W + 58, y: anchor.y } : canvas.viewCenter());
		const id = `${kind}-${Date.now().toString(36)}`;
		workflow.nodes = [
			...workflow.nodes,
			{ id, kind, title: t.label, subtitle: t.subtitle, desc: t.desc, x: Math.round(at.x / 10) * 10, y: Math.round(at.y / 10) * 10, config: defaultConfig(kind) }
		];
		// n8n-style: adding while a node is selected chains it after that node
		if (anchor && t.category !== 'trigger') {
			const handle = typeOf(anchor.kind).branching ? 'true' : 'out';
			workflow.edges = [...workflow.edges, { id: `${anchor.id}-${id}`, from: anchor.id, to: id, handle, label: handle === 'true' ? 'Yes' : undefined }];
		}
		selectedNodeId = id;
		selectedEdgeId = null;
		panelTab = 'config';
		panelOpen = true;
		markDirty();
		dispatch('toast', { message: `Added “${t.label}”${anchor && t.category !== 'trigger' ? ` after “${anchor.title}”` : ''}`, kind: 'info' });
	}

	function removeNode(id: string) {
		const n = workflow.nodes.find((x) => x.id === id);
		workflow.nodes = workflow.nodes.filter((x) => x.id !== id);
		workflow.edges = workflow.edges.filter((e) => e.from !== id && e.to !== id);
		if (selectedNodeId === id) selectedNodeId = null;
		markDirty();
		if (n) dispatch('toast', { message: `Deleted “${n.title}”`, kind: 'info' });
	}

	function duplicateNode(id: string) {
		const n = workflow.nodes.find((x) => x.id === id);
		if (!n) return;
		const copy = { ...clone(n), id: `${n.kind}-${Date.now().toString(36)}`, x: n.x + 40, y: n.y + 40, title: `${n.title} (copy)` };
		workflow.nodes = [...workflow.nodes, copy];
		selectedNodeId = copy.id;
		markDirty();
	}

	function save() {
		dirty = false;
		savedAt = `Today, ${new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
		workflow.updated = savedAt;
		workflow = workflow;
		dispatch('change');
		dispatch('toast', { message: 'Workflow saved', kind: 'success' });
	}

	function publish(target = 'Published') {
		publishMenu = false;
		const [maj, min] = workflow.version.replace('v', '').split('.').map(Number);
		workflow.version = `v${maj || 1}.${(min || 0) + 1}`;
		workflow.status = 'active';
		save();
		dispatch('toast', { message: `${target} ${workflow.version} — workflow is live`, kind: 'success' });
	}

	function exportJson() {
		moreMenu = false;
		const { nodes, edges, name, description, version } = workflow;
		const blob = new Blob([JSON.stringify({ name, description, version, nodes, edges }, null, 2)], { type: 'application/json' });
		const a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = `${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.workflow.json`;
		a.click();
		URL.revokeObjectURL(a.href);
		dispatch('toast', { message: 'Workflow exported as JSON', kind: 'success' });
	}

	async function focusNode(id: string) {
		selectedNodeId = id;
		await tick();
		canvas?.centerOn(id);
	}

	function onKey(e: KeyboardEvent) {
		const t = e.target as HTMLElement;
		const typing = t.closest('input, textarea, select, [contenteditable]');
		if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
			e.preventDefault();
			save();
		} else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
			e.preventDefault();
			run();
		} else if (!typing && (e.key === 'Delete' || e.key === 'Backspace')) {
			if (selectedNodeId) removeNode(selectedNodeId);
			else if (selectedEdgeId) {
				workflow.edges = workflow.edges.filter((x) => x.id !== selectedEdgeId);
				selectedEdgeId = null;
				markDirty();
			}
		} else if (!typing && e.key === 'Escape') {
			selectedNodeId = null;
			selectedEdgeId = null;
			publishMenu = moreMenu = false;
		}
	}

	function closeMenus(e: MouseEvent) {
		if (!(e.target as HTMLElement).closest('.lg-split, .lg-more')) publishMenu = moreMenu = false;
	}

	// selecting a node opens its config, like Dify
	let lastSelected: string | null = null;
	$: if (selectedNodeId !== lastSelected) {
		lastSelected = selectedNodeId;
		if (selectedNodeId && panelTab === 'run' && runStatus !== 'running') panelTab = 'config';
	}

	onMount(() => {
		window.addEventListener('keydown', onKey);
		window.addEventListener('click', closeMenus);
	});
	onDestroy(() => {
		runToken++;
		if (typeof window === 'undefined') return;
		window.removeEventListener('keydown', onKey);
		window.removeEventListener('click', closeMenus);
	});
</script>

<div class="editor lg-card">
	<div class="bar">
		<button class="lg-btn sm" style="border:0;padding:0 6px;color:#475569" on:click={() => dispatch('back')}>
			<LGIcon name="chevronLeft" size={14} /> Workflows
		</button>
		<span class="vsep"></span>
		<span class="wf-icon"><LGIcon name="workflow" size={15} /></span>
		{#if editingName}
			<!-- svelte-ignore a11y-autofocus -->
			<input
				class="lg-input name-input"
				bind:value={workflow.name}
				autofocus
				on:blur={() => { editingName = false; markDirty(); }}
				on:keydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
			/>
		{:else}
			<span class="name">{workflow.name}</span>
			<button class="lg-icon-btn sm" on:click={() => (editingName = true)} title="Rename"><LGIcon name="pencil" size={13} /></button>
		{/if}
		{#if workflow.status === 'active'}
			<span class="lg-pill green"><span class="lg-dot" style="background:#22c55e"></span> Active</span>
		{:else if workflow.status === 'paused'}
			<span class="lg-pill amber">Paused</span>
		{:else}
			<span class="lg-pill gray">Draft</span>
		{/if}
		<span class="saved lg-hide-sm">{dirty ? '● Unsaved changes' : `Saved · ${savedAt}`}</span>

		<span class="lg-spacer"></span>

		<button class="lg-btn sm" on:click={save} title="Save (Ctrl+S)"><LGIcon name="save" size={13} /> Save</button>
		<button class="lg-btn sm outline-primary" on:click={run} disabled={runStatus === 'running'} title="Test run (Ctrl+Enter)">
			<LGIcon name="beaker" size={13} /> {runStatus === 'running' ? 'Running…' : 'Test Run'}
		</button>
		<div class="lg-split">
			<button class="lg-btn sm primary" on:click={() => publish()}><LGIcon name="rocket" size={13} /> Publish</button>
			<button class="lg-btn sm primary" on:click={() => (publishMenu = !publishMenu)} aria-label="Publish options"><LGIcon name="chevronDown" size={13} /></button>
			{#if publishMenu}
				<div class="lg-menu">
					<button on:click={() => publish()}><LGIcon name="rocket" size={14} /><div><div>Publish update</div><div class="lg-menu-sub">Current: {workflow.version}</div></div></button>
					<button on:click={() => publish('API endpoint live for')}><LGIcon name="link" size={14} /><div><div>Publish as API</div><div class="lg-menu-sub">POST /v1/workflows/run</div></div></button>
					<button on:click={() => publish('Embed widget updated to')}><LGIcon name="code" size={14} /><div><div>Embed on website</div><div class="lg-menu-sub">Script tag for your site</div></div></button>
				</div>
			{/if}
		</div>
		<div class="lg-more" style="position:relative">
			<button class="lg-icon-btn sm" on:click={() => (moreMenu = !moreMenu)} aria-label="More"><LGIcon name="dots" size={16} /></button>
			{#if moreMenu}
				<div class="lg-menu">
					<button on:click={exportJson}><LGIcon name="save" size={14} /> Export as JSON</button>
					<button on:click={() => { moreMenu = false; canvas.fitView(); }}><LGIcon name="expand" size={14} /> Fit to view</button>
					<button on:click={() => { moreMenu = false; resetRun(); runStatus = 'idle'; }}><LGIcon name="refresh" size={14} /> Clear run results</button>
					<button on:click={() => { moreMenu = false; workflow.status = workflow.status === 'paused' ? 'active' : 'paused'; markDirty(); }}>
						<LGIcon name={workflow.status === 'paused' ? 'play' : 'stop'} size={14} /> {workflow.status === 'paused' ? 'Resume workflow' : 'Pause workflow'}
					</button>
				</div>
			{/if}
		</div>
	</div>

	<div class="body">
		<div class="lg-hide-sm pal"><NodePalette on:add={(e) => addNode(e.detail)} /></div>
		<Canvas
			bind:this={canvas}
			bind:nodes={workflow.nodes}
			bind:edges={workflow.edges}
			bind:selectedNodeId
			bind:selectedEdgeId
			{nodeStatus}
			{edgeStatus}
			{nodeMs}
			on:change={markDirty}
			on:drop={(e) => addNode(e.detail.kind, e.detail)}
			on:connected={(e) => dispatch('toast', { message: `Connected “${titleOf(e.detail.from)}” → “${titleOf(e.detail.to)}”`, kind: 'info' })}
		/>
		{#if panelOpen}
			<RightPanel
				{workflow}
				{selectedNodeId}
				bind:tab={panelTab}
				{runStatus}
				{elapsedMs}
				{logs}
				{steps}
				{finalOutput}
				{nodeOutputs}
				bind:inputPreset
				bind:inputText
				bind:inputError
				on:run={run}
				on:stop={stop}
				on:change={markDirty}
				on:remove={(e) => removeNode(e.detail)}
				on:duplicate={(e) => duplicateNode(e.detail)}
				on:focus={(e) => focusNode(e.detail)}
				on:collapse={() => (panelOpen = false)}
			/>
		{:else}
			<button class="reopen" on:click={() => (panelOpen = true)} title="Show panel"><LGIcon name="chevronLeft" size={14} /><span>Run · Config</span></button>
		{/if}
	</div>
</div>

<style>
	.editor {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.bar {
		height: 52px;
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0 12px;
		border-bottom: 1px solid #e6e9f0;
	}
	.vsep {
		width: 1px;
		height: 20px;
		background: #e2e8f0;
		margin: 0 4px;
	}
	.wf-icon {
		width: 28px;
		height: 28px;
		border-radius: 8px;
		display: grid;
		place-items: center;
		background: #f1f5f9;
		color: #475569;
	}
	.name {
		font-weight: 700;
		font-size: 14.5px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 280px;
	}
	.name-input {
		width: 260px !important;
		height: 30px;
		font-weight: 600;
	}
	.saved {
		font-size: 11.5px;
		color: #94a3b8;
		margin-left: 4px;
		white-space: nowrap;
	}
	.body {
		flex: 1;
		min-height: 0;
		display: flex;
	}
	.pal {
		display: flex;
	}
	.reopen {
		width: 30px;
		border-left: 1px solid #e6e9f0 !important;
		display: flex !important;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		padding-top: 14px !important;
		color: #64748b;
		background: #fff !important;
	}
	.reopen span {
		writing-mode: vertical-rl;
		font-size: 11.5px;
		font-weight: 600;
	}
	@media (max-width: 1280px) {
		.saved {
			display: none;
		}
	}
</style>
