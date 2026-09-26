<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import JsonView from './JsonView.svelte';
	import { TONES, typeOf } from '../data/catalog';
	import { TEST_INPUTS } from '../data/samples';
	import type { LogLine, RunStatus, RunStep, Workflow } from '../types';

	export let workflow: Workflow;
	export let selectedNodeId: string | null;
	export let tab: 'run' | 'config' | 'output' = 'run';
	export let runStatus: RunStatus = 'idle';
	export let elapsedMs = 0;
	export let logs: LogLine[] = [];
	export let steps: RunStep[] = [];
	export let finalOutput: Record<string, any> | null = null;
	export let nodeOutputs: Record<string, Record<string, any>> = {};
	export let inputPreset = 'Form Data';
	export let inputText = TEST_INPUTS['Form Data'];
	export let inputError = '';

	const dispatch = createEventDispatcher<{
		run: void;
		stop: void;
		change: void;
		remove: string;
		duplicate: string;
		collapse: void;
		focus: string;
	}>();

	let editing = false;
	let resultTab: 'output' | 'logs' | 'traces' = 'output';
	let runMenu = false;
	let copied = false;

	$: node = workflow.nodes.find((n) => n.id === selectedNodeId) ?? null;
	$: nodeIndex = node ? workflow.nodes.indexOf(node) + 1 : 0;
	$: type = node ? typeOf(node.kind) : null;
	$: tone = type ? TONES[type.tone] : null;
	$: inputsFrom = node ? workflow.edges.filter((e) => e.to === node!.id).map((e) => workflow.nodes.find((n) => n.id === e.from)).filter(Boolean) : [];
	$: outputsTo = node ? workflow.edges.filter((e) => e.from === node!.id).map((e) => ({ e, n: workflow.nodes.find((n) => n.id === e.to) })).filter((x) => x.n) : [];
	$: totalMs = steps.reduce((a, s) => a + s.ms, 0) || 1;
	// follow the run: logs while it executes, output when it finishes
	let prevStatus: RunStatus = runStatus;
	$: if (runStatus !== prevStatus) {
		if (runStatus === 'running') resultTab = 'logs';
		else if (runStatus === 'success') resultTab = 'output';
		prevStatus = runStatus;
	}

	const SELECTS: Record<string, string[]> = {
		model: ['claude-sonnet-5', 'claude-opus-5-5', 'claude-haiku-4-5', 'Rules + LLM', 'gpt-4.1', 'gemini-2.5-pro'],
		method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
		operator: ['>', '>=', '<', '<=', '==', '!=', 'in', 'contains'],
		provider: ['HubSpot', 'Salesforce', 'Zoho CRM', 'Pipedrive', 'Postgres'],
		language: ['Python 3', 'JavaScript'],
		unit: ['minutes', 'hours', 'days'],
		mode: ['Send now', 'Save as draft', 'Append row', 'Upsert'],
		object: ['Contact', 'Lead', 'Deal', 'Company'],
		auth: ['None', 'API Key', 'Bearer Token', 'HMAC Signature'],
		platform: ['HubSpot Sequences', 'Mailchimp', 'Brevo', 'Apollo Sequences']
	};
	const LONG = ['prompt', 'code', 'message', 'query', 'routes', 'weights', 'classes'];
	const label = (k: string) => k.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

	function setConfig(key: string, raw: string, numeric: boolean) {
		if (!node) return;
		node.config[key] = numeric ? Number(raw) : raw;
		dispatch('change');
	}
	function setField(key: 'title' | 'subtitle' | 'desc', v: string) {
		if (!node) return;
		node[key] = v;
		dispatch('change');
	}
	function pickPreset(p: string) {
		inputPreset = p;
		inputText = TEST_INPUTS[p];
		inputError = '';
	}
	async function copy(v: unknown) {
		try {
			await navigator.clipboard.writeText(JSON.stringify(v, null, 2));
			copied = true;
			setTimeout(() => (copied = false), 1400);
		} catch {
			/* clipboard unavailable */
		}
	}
	const fmt = (ms: number) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)}s`);
</script>

<aside class="panel">
	<div class="ptabs">
		<button class:active={tab === 'run'} on:click={() => (tab = 'run')}>Run</button>
		<button class:active={tab === 'config'} on:click={() => (tab = 'config')}>Node Config</button>
		<button class:active={tab === 'output'} on:click={() => (tab = 'output')}>Output</button>
		<span class="lg-spacer"></span>
		<button class="lg-icon-btn sm" on:click={() => dispatch('collapse')} title="Hide panel"><LGIcon name="chevronRight" size={14} /></button>
	</div>

	<div class="pbody">
		{#if tab === 'run'}
			<div class="lg-split" style="width:100%">
				{#if runStatus === 'running'}
					<button class="lg-btn danger" style="flex:1;justify-content:center;border-radius:9px" on:click={() => dispatch('stop')}>
						<LGIcon name="stop" size={14} /> Stop Run
					</button>
				{:else}
					<button class="lg-btn primary" style="flex:1;justify-content:center" on:click={() => dispatch('run')}>
						<LGIcon name="play" size={14} /> Run Workflow
					</button>
					<button class="lg-btn primary" on:click={() => (runMenu = !runMenu)} aria-label="Run options"><LGIcon name="chevronDown" size={14} /></button>
					{#if runMenu}
						<div class="lg-menu" style="left:0;right:0">
							{#each Object.keys(TEST_INPUTS) as p}
								<button on:click={() => { runMenu = false; pickPreset(p); dispatch('run'); }}>
									<LGIcon name="play" size={13} />
									<div><div>Run with “{p}”</div><div class="lg-menu-sub">{p === 'Manual Input' ? 'Low-fit lead → nurture path' : p === 'Email' ? 'Parsed from an inbound email' : 'Sample website form lead'}</div></div>
								</button>
							{/each}
						</div>
					{/if}
				{/if}
			</div>

			<div class="sec-head">
				<span>Test Input</span>
				<button class="lg-btn sm" on:click={() => (editing = !editing)}>
					<LGIcon name={editing ? 'check' : 'pencil'} size={13} />{editing ? 'Done' : 'Edit'}
				</button>
			</div>
			<div class="box">
				<div class="mini-tabs">
					{#each Object.keys(TEST_INPUTS) as p}
						<button class:active={inputPreset === p} on:click={() => pickPreset(p)}>{p}</button>
					{/each}
				</div>
				{#if editing}
					<textarea class="lg-textarea" rows="9" bind:value={inputText} spellcheck="false" style="border:0;border-radius:0 0 8px 8px;box-shadow:none"></textarea>
				{:else}
					{#key inputText}
						<div style="padding:8px">
							{#if inputError}
								<pre class="raw">{inputText}</pre>
							{:else}
								<JsonView value={(() => { try { return JSON.parse(inputText); } catch { return inputText; } })()} maxHeight={170} />
							{/if}
						</div>
					{/key}
				{/if}
			</div>
			{#if inputError}
				<div class="err"><LGIcon name="xCircle" size={14} /> {inputError}</div>
			{/if}

			<div class="sec-head">
				<span>Execution Result</span>
				{#if runStatus === 'running'}
					<span class="lg-pill blue"><span class="spin"></span> Running</span>
				{:else if runStatus === 'success'}
					<span class="lg-pill green"><LGIcon name="checkCircle" size={13} /> Success</span>
				{:else if runStatus === 'failed'}
					<span class="lg-pill red"><LGIcon name="xCircle" size={13} /> Failed</span>
				{:else}
					<span class="lg-pill gray">Not run yet</span>
				{/if}
			</div>
			<div class="lg-hint" style="margin:-4px 0 8px">
				{#if runStatus === 'idle'}Run the workflow to see results{:else}Execution time: {(elapsedMs / 1000).toFixed(1)}s · {steps.length} / {workflow.nodes.length} nodes{/if}
			</div>

			<div class="box">
				<div class="mini-tabs">
					<button class:active={resultTab === 'output'} on:click={() => (resultTab = 'output')}>Output</button>
					<button class:active={resultTab === 'logs'} on:click={() => (resultTab = 'logs')}>Logs <span class="lg-count">{logs.length}</span></button>
					<button class:active={resultTab === 'traces'} on:click={() => (resultTab = 'traces')}>Traces</button>
				</div>
				<div style="padding:8px">
					{#if resultTab === 'output'}
						{#if finalOutput}
							<JsonView value={finalOutput} maxHeight={300} />
						{:else}
							<div class="empty">{runStatus === 'running' ? 'Waiting for the workflow to finish…' : 'No output yet.'}</div>
						{/if}
					{:else if resultTab === 'logs'}
						<div class="logs">
							{#each logs as l}
								<div class="log {l.level}">
									<span class="t">{l.time}</span>
									{#if l.node}<span class="n">{l.node}</span>{/if}
									<span class="m">{l.message}</span>
								</div>
							{:else}
								<div class="empty">No logs yet.</div>
							{/each}
						</div>
					{:else}
						<div class="traces">
							{#each steps as s, i}
								{@const n = workflow.nodes.find((x) => x.id === s.nodeId)}
								{@const offset = steps.slice(0, i).reduce((a, x) => a + x.ms, 0)}
								{#if n}
									<button class="trace" on:click={() => dispatch('focus', n.id)}>
										<span class="tn">{n.title}</span>
										<span class="bar"><span style="left:{(offset / totalMs) * 100}%;width:{Math.max(2, (s.ms / totalMs) * 100)}%;background:{TONES[typeOf(n.kind).tone].icon}"></span></span>
										<span class="tm">{fmt(s.ms)}</span>
									</button>
								{/if}
							{:else}
								<div class="empty">Traces appear after a run.</div>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		{:else if tab === 'config'}
			{#if node && type && tone}
				<div class="node-head" style="background:{tone.bg};border-color:{tone.border}">
					<span class="nh-icon" style="background:{tone.soft};color:{tone.icon}"><LGIcon name={type.icon} size={17} stroke={2} /></span>
					<div style="flex:1;min-width:0">
						<div style="font-weight:700">{nodeIndex}. {node.title}</div>
						<div class="lg-hint">{type.label} · <code>{node.id}</code></div>
					</div>
				</div>

				<div class="field"><span class="lg-label">Step name</span><input class="lg-input" value={node.title} on:input={(e) => setField('title', e.currentTarget.value)} /></div>
				<div class="field"><span class="lg-label">Subtitle</span><input class="lg-input" value={node.subtitle} on:input={(e) => setField('subtitle', e.currentTarget.value)} /></div>
				<div class="field"><span class="lg-label">Description</span><input class="lg-input" value={node.desc} on:input={(e) => setField('desc', e.currentTarget.value)} /></div>

				<div class="sec-head" style="margin-top:14px"><span>Parameters</span></div>
				{#each Object.entries(node.config) as [key, val] (key)}
					<div class="field">
						<span class="lg-label">{label(key)}</span>
						{#if SELECTS[key]}
							<select class="lg-select" value={String(val)} on:change={(e) => setConfig(key, e.currentTarget.value, false)}>
								{#each SELECTS[key].includes(String(val)) ? SELECTS[key] : [String(val), ...SELECTS[key]] as o}<option>{o}</option>{/each}
							</select>
						{:else if typeof val === 'number'}
							<input class="lg-input" type="number" value={val} on:input={(e) => setConfig(key, e.currentTarget.value, true)} />
						{:else if LONG.includes(key) || String(val).length > 60}
							<textarea class="lg-textarea" rows={key === 'code' ? 6 : 4} value={String(val)} on:input={(e) => setConfig(key, e.currentTarget.value, false)} spellcheck="false"></textarea>
						{:else}
							<input class="lg-input" value={String(val)} on:input={(e) => setConfig(key, e.currentTarget.value, false)} />
						{/if}
					</div>
				{/each}
				{#if !Object.keys(node.config).length}<div class="lg-hint">This node has no parameters.</div>{/if}

				<div class="sec-head" style="margin-top:14px"><span>Connections</span></div>
				<div class="conns">
					<div><span class="lg-hint">Inputs</span>
						{#each inputsFrom as n}<button class="chip" on:click={() => n && dispatch('focus', n.id)}>{n?.title}</button>{:else}<span class="lg-hint">—</span>{/each}
					</div>
					<div><span class="lg-hint">Outputs</span>
						{#each outputsTo as { e, n }}<button class="chip" on:click={() => n && dispatch('focus', n.id)}>{e.label ? `${e.label} → ` : ''}{n?.title}</button>{:else}<span class="lg-hint">—</span>{/each}
					</div>
				</div>

				<div style="display:flex;gap:8px;margin-top:16px">
					<button class="lg-btn sm" on:click={() => node && dispatch('duplicate', node.id)}><LGIcon name="copy" size={13} /> Duplicate</button>
					<button class="lg-btn sm danger" on:click={() => node && dispatch('remove', node.id)}><LGIcon name="trash" size={13} /> Delete</button>
				</div>
			{:else}
				<div class="empty big">
					<LGIcon name="cursor" size={26} />
					<div style="font-weight:600;color:#334155;margin-top:6px">No node selected</div>
					<div>Click a node on the canvas to edit its settings.</div>
				</div>
			{/if}
		{:else}
			{@const out = node ? nodeOutputs[node.id] : finalOutput}
			<div class="sec-head" style="margin-top:0">
				<span>{node ? `${nodeIndex}. ${node.title}` : 'Workflow output'}</span>
				{#if out}
					<button class="lg-btn sm" on:click={() => copy(out)}><LGIcon name={copied ? 'check' : 'copy'} size={13} />{copied ? 'Copied' : 'Copy'}</button>
				{/if}
			</div>
			<div class="lg-hint" style="margin:-4px 0 10px">{node ? 'Output of the selected node from the last run' : 'Select a node to inspect its own output'}</div>
			{#if out}
				<JsonView value={out} maxHeight={520} />
			{:else}
				<div class="empty big">
					<LGIcon name="beaker" size={26} />
					<div>{node && runStatus !== 'idle' ? 'This node did not run on the last execution.' : 'Run the workflow to see output here.'}</div>
					<button class="lg-btn sm primary" style="margin-top:8px" on:click={() => { tab = 'run'; dispatch('run'); }}><LGIcon name="play" size={13} /> Test Run</button>
				</div>
			{/if}
		{/if}
	</div>
</aside>

<style>
	.panel {
		width: 340px;
		flex-shrink: 0;
		border-left: 1px solid #e6e9f0;
		display: flex;
		flex-direction: column;
		min-height: 0;
		background: #fff;
	}
	.ptabs {
		display: flex;
		align-items: center;
		gap: 18px;
		padding: 0 10px 0 16px;
		border-bottom: 1px solid #e6e9f0;
		height: 44px;
		flex-shrink: 0;
	}
	.ptabs > button:not(.lg-icon-btn) {
		height: 44px;
		font-weight: 500;
		color: #64748b;
		border-bottom: 2px solid transparent !important;
	}
	.ptabs > button.active {
		color: #2563eb;
		border-bottom-color: #2563eb !important;
	}
	.pbody {
		flex: 1;
		overflow-y: auto;
		padding: 14px 16px 18px;
	}
	.sec-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-weight: 700;
		font-size: 13px;
		margin: 16px 0 8px;
	}
	.box {
		border: 1px solid #e6e9f0;
		border-radius: 9px;
		overflow: hidden;
	}
	.mini-tabs {
		display: flex;
		gap: 2px;
		padding: 4px;
		background: #f8fafc;
		border-bottom: 1px solid #eef1f5;
	}
	.mini-tabs button {
		flex: 1;
		padding: 5px 6px !important;
		border-radius: 6px;
		font-size: 12px;
		color: #64748b;
		font-weight: 500;
		white-space: nowrap;
	}
	.mini-tabs button.active {
		background: #fff !important;
		color: #2563eb;
		box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
	}
	.raw {
		margin: 0;
		font-size: 11.5px;
		white-space: pre-wrap;
		color: #b91c1c;
	}
	.err {
		display: flex;
		align-items: center;
		gap: 6px;
		color: #b91c1c;
		font-size: 12px;
		margin-top: 6px;
	}
	.empty {
		color: #94a3b8;
		font-size: 12px;
		text-align: center;
		padding: 14px 6px;
	}
	.empty.big {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		padding: 40px 10px;
	}
	.logs {
		max-height: 300px;
		overflow: auto;
		font-family: ui-monospace, Menlo, monospace;
		font-size: 11px;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.log {
		display: flex;
		gap: 6px;
		align-items: baseline;
		padding: 3px 4px;
		border-radius: 4px;
	}
	.log .t {
		color: #94a3b8;
		flex-shrink: 0;
	}
	.log .n {
		color: #7c3aed;
		font-weight: 600;
		flex-shrink: 0;
	}
	.log .m {
		color: #334155;
	}
	.log.success .m {
		color: #15803d;
	}
	.log.error {
		background: #fef2f2;
	}
	.log.error .m {
		color: #b91c1c;
	}
	.log.warn .m {
		color: #b45309;
	}
	.traces {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.trace {
		display: grid !important;
		grid-template-columns: 96px 1fr 48px;
		align-items: center;
		gap: 8px;
		padding: 4px !important;
		border-radius: 6px;
		text-align: left;
	}
	.trace:hover {
		background: #f5f8ff !important;
	}
	.tn {
		font-size: 11.5px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.bar {
		position: relative;
		height: 8px;
		background: #f1f5f9;
		border-radius: 4px;
	}
	.bar span {
		position: absolute;
		top: 0;
		bottom: 0;
		border-radius: 4px;
	}
	.tm {
		font-size: 11px;
		font-family: ui-monospace, Menlo, monospace;
		color: #64748b;
		text-align: right;
	}
	.node-head {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 12px;
		border: 1px solid;
		border-radius: 10px;
		margin-bottom: 12px;
	}
	.nh-icon {
		width: 34px;
		height: 34px;
		border-radius: 9px;
		display: grid;
		place-items: center;
	}
	.field {
		margin-bottom: 10px;
	}
	.conns {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.conns > div {
		display: flex;
		flex-wrap: wrap;
		gap: 5px;
		align-items: center;
	}
	.conns .lg-hint:first-child {
		width: 56px;
	}
	.chip {
		font-size: 11.5px;
		padding: 2px 9px !important;
		border-radius: 999px;
		background: #f1f5f9 !important;
		border: 1px solid #e2e8f0 !important;
	}
	.chip:hover {
		background: #eff6ff !important;
		border-color: #bfdbfe !important;
	}
	.spin {
		width: 10px;
		height: 10px;
		border-radius: 999px;
		border: 2px solid #bfdbfe;
		border-top-color: #2563eb;
		animation: lg-spin 0.7s linear infinite;
		display: inline-block;
	}
	@keyframes lg-spin {
		to {
			transform: rotate(360deg);
		}
	}
	code {
		font-size: 11px;
	}
</style>
