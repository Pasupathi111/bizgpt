<script lang="ts">
	// Root of the Lead Generation module: BizGPT shell + Dify-style workflow builder.
	import { onMount } from 'svelte';
	import './styles/lead-generation.css';
	import LGIcon from './components/LGIcon.svelte';
	import WorkflowList from './components/WorkflowList.svelte';
	import WorkflowEditor from './components/WorkflowEditor.svelte';
	import TemplateGallery from './components/TemplateGallery.svelte';
	import ExecutionHistory from './components/ExecutionHistory.svelte';
	import VariablesView from './components/VariablesView.svelte';
	import SettingsView from './components/SettingsView.svelte';
	import { SAMPLE_WORKFLOWS, TEMPLATES, clone, defaultConfig } from './data/workflows';
	import { RUN_HISTORY, VARIABLES, type Variable } from './data/samples';
	import type { RunRecord, Workflow } from './types';

	type Tab = 'workflows' | 'templates' | 'history' | 'variables' | 'settings';
	const STORE_KEY = 'bizgpt.lead-generation.v1';

	let tab: Tab = 'workflows';
	let workflows: Workflow[] = clone(SAMPLE_WORKFLOWS);
	let runs: RunRecord[] = clone(RUN_HISTORY);
	let variables: Variable[] = clone(VARIABLES);
	let openId: string | null = null;
	let query = '';
	let toasts: { id: number; message: string; kind: string }[] = [];
	let toastSeq = 0;
	let loaded = false;

	$: current = workflows.find((w) => w.id === openId) ?? null;
	$: if (loaded) persist(workflows, runs, variables);

	function persist(w: Workflow[], r: RunRecord[], v: Variable[]) {
		try {
			localStorage.setItem(STORE_KEY, JSON.stringify({ w, r: r.slice(0, 50), v }));
		} catch {
			/* storage unavailable: demo still works in-memory */
		}
	}

	function toast(message: string, kind = 'info') {
		const id = ++toastSeq;
		toasts = [...toasts.slice(-3), { id, message, kind }];
		setTimeout(() => (toasts = toasts.filter((t) => t.id !== id)), 3200);
	}

	function open(id: string) {
		tab = 'workflows';
		openId = id;
	}

	function useTemplate(id: string) {
		const t = TEMPLATES.find((x) => x.id === id);
		if (!t) return;
		const wf: Workflow = {
			...clone(t.workflow),
			id: `wf-${Date.now().toString(36)}`,
			name: t.name,
			status: 'draft',
			runs: 0,
			successRate: 0,
			leads: 0,
			lastRun: 'Never',
			owner: 'Pasupathi S',
			updated: 'Just now',
			version: 'v0.1'
		};
		workflows = [wf, ...workflows];
		open(wf.id);
		toast(`Created “${t.name}” from template`, 'success');
	}

	function createBlank() {
		const wf: Workflow = {
			id: `wf-${Date.now().toString(36)}`,
			name: 'Untitled lead workflow',
			description: 'New lead-generation workflow.',
			category: 'Inbound',
			status: 'draft',
			trigger: 'Form Submission',
			runs: 0,
			successRate: 0,
			leads: 0,
			lastRun: 'Never',
			owner: 'Pasupathi S',
			updated: 'Just now',
			version: 'v0.1',
			tags: [],
			nodes: [{ id: 'n1', kind: 'form-trigger', title: 'Trigger', subtitle: 'Form Submission', desc: 'New lead form submission', x: 40, y: 80, config: defaultConfig('form-trigger') }],
			edges: []
		};
		workflows = [wf, ...workflows];
		open(wf.id);
		toast('Blank workflow created — drag nodes from the left panel', 'info');
	}

	function toggle(id: string) {
		const w = workflows.find((x) => x.id === id);
		if (!w) return;
		w.status = w.status === 'active' ? 'paused' : 'active';
		workflows = workflows;
		toast(`“${w.name}” ${w.status === 'active' ? 'activated' : 'paused'}`, w.status === 'active' ? 'success' : 'info');
	}

	function duplicate(id: string) {
		const w = workflows.find((x) => x.id === id);
		if (!w) return;
		const copy = { ...clone(w), id: `wf-${Date.now().toString(36)}`, name: `${w.name} (copy)`, status: 'draft' as const, runs: 0, leads: 0, successRate: 0, lastRun: 'Never', version: 'v0.1' };
		workflows = [...workflows, copy];
		toast(`Duplicated “${w.name}”`, 'success');
	}

	function remove(id: string) {
		const w = workflows.find((x) => x.id === id);
		workflows = workflows.filter((x) => x.id !== id);
		if (w) toast(`Deleted “${w.name}”`, 'info');
	}

	function onRan(r: RunRecord) {
		runs = [r, ...runs];
		const w = workflows.find((x) => x.id === r.workflowId);
		if (w) {
			w.runs += 1;
			w.lastRun = 'Just now';
			if (r.status === 'success' && (r.score ?? 0) > 70) w.leads += 1;
			workflows = workflows;
		}
	}

	function setTab(t: Tab) {
		tab = t;
		if (t !== 'workflows') openId = null;
	}

	onMount(() => {
		try {
			const saved = JSON.parse(localStorage.getItem(STORE_KEY) ?? 'null');
			if (saved?.w?.length) {
				workflows = saved.w;
				runs = saved.r ?? runs;
				variables = saved.v ?? variables;
			}
		} catch {
			/* ignore corrupt or blocked storage */
		}
		loaded = true;
	});

	function resetDemo() {
		workflows = clone(SAMPLE_WORKFLOWS);
		runs = clone(RUN_HISTORY);
		variables = clone(VARIABLES);
		openId = null;
		toast('Demo data reset', 'info');
	}

	const tabs: { key: Tab; label: string }[] = [
		{ key: 'workflows', label: 'My Workflows' },
		{ key: 'templates', label: 'Templates' },
		{ key: 'history', label: 'Execution History' },
		{ key: 'variables', label: 'Variables' },
		{ key: 'settings', label: 'Settings' }
	];
	const tabCount = (k: Tab) => (k === 'workflows' ? workflows.length : k === 'templates' ? TEMPLATES.length : k === 'history' ? runs.length : null);
</script>

<div class="lg-app">
	<main class="lg-main">
		<div class="lg-page-head">
			<span class="lg-page-icon"><LGIcon name="workflow" size={22} /></span>
			<div style="flex:1;min-width:0">
				<h1 class="lg-page-title">Dify Workflow <span class="lg-pill blue">Lead Generation</span></h1>
				<p class="lg-page-sub">Build and manage AI workflows to automate your business processes — capture, enrich, score and route every lead.</p>
			</div>
			<button class="lg-btn lg-hide-sm" on:click={resetDemo} title="Restore the sample workflows"><LGIcon name="refresh" size={14} /> Reset demo</button>
			<button class="lg-btn primary" on:click={createBlank}><LGIcon name="plus" size={15} /> Create Workflow</button>
		</div>

		<nav class="lg-tabs">
			{#each tabs as t}
				{@const c = tabCount(t.key)}
				<button class="lg-tab" class:active={tab === t.key} on:click={() => setTab(t.key)}>
					{t.label}{#if c !== null}<span class="lg-count">{c}</span>{/if}
				</button>
			{/each}
		</nav>

		<section class="lg-content" class:flush={tab === 'workflows' && current}>
			{#if tab === 'workflows'}
				{#if current}
					{#key current.id}
						<WorkflowEditor
							workflow={current}
							on:back={() => (openId = null)}
							on:toast={(e) => toast(e.detail.message, e.detail.kind)}
							on:ran={(e) => onRan(e.detail)}
							on:change={() => (workflows = workflows)}
						/>
					{/key}
				{:else}
					<WorkflowList
						{workflows}
						bind:query
						on:open={(e) => open(e.detail)}
						on:toggle={(e) => toggle(e.detail)}
						on:duplicate={(e) => duplicate(e.detail)}
						on:remove={(e) => remove(e.detail)}
						on:create={createBlank}
						on:templates={() => setTab('templates')}
					/>
				{/if}
			{:else if tab === 'templates'}
				<TemplateGallery {query} on:use={(e) => useTemplate(e.detail)} />
			{:else if tab === 'history'}
				<ExecutionHistory {runs} bind:query on:open={(e) => open(e.detail)} />
			{:else if tab === 'variables'}
				<VariablesView bind:variables on:toast={(e) => toast(e.detail.message, e.detail.kind)} />
			{:else}
				<SettingsView on:toast={(e) => toast(e.detail.message, e.detail.kind)} />
			{/if}
		</section>
	</main>

	<div class="lg-toasts" aria-live="polite">
		{#each toasts as t (t.id)}
			<div class="lg-toast {t.kind}">
				<LGIcon name={t.kind === 'success' ? 'checkCircle' : t.kind === 'error' ? 'xCircle' : 'sparkles'} size={17} />
				<span>{t.message}</span>
			</div>
		{/each}
	</div>
</div>
