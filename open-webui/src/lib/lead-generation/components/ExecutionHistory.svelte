<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import type { RunRecord } from '../types';

	export let runs: RunRecord[];
	export let query = '';
	const dispatch = createEventDispatcher<{ open: string }>();

	let status: 'all' | 'success' | 'failed' = 'all';
	$: shown = runs.filter(
		(r) => (status === 'all' || r.status === status) && (!query || `${r.workflowName} ${r.lead} ${r.id}`.toLowerCase().includes(query.toLowerCase()))
	);
	$: ok = runs.filter((r) => r.status === 'success').length;
	$: avg = runs.length ? runs.reduce((a, r) => a + r.durationMs, 0) / runs.length : 0;
	const fmt = (ms: number) => (ms < 60000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`);
</script>

<div class="summary">
	<div class="lg-card sm-card"><span class="lg-hint">Executions</span><b>{runs.length}</b></div>
	<div class="lg-card sm-card"><span class="lg-hint">Succeeded</span><b style="color:#16a34a">{ok}</b></div>
	<div class="lg-card sm-card"><span class="lg-hint">Failed</span><b style="color:#dc2626">{runs.length - ok}</b></div>
	<div class="lg-card sm-card"><span class="lg-hint">Avg. duration</span><b>{fmt(avg)}</b></div>
</div>

<div class="controls">
	<div class="lg-segment">
		{#each [['all', 'All'], ['success', 'Succeeded'], ['failed', 'Failed']] as [k, l]}
			<button class:active={status === k} on:click={() => (status = k)}>{l}</button>
		{/each}
	</div>
	<div class="lg-search" style="width:260px;background:#fff">
		<LGIcon name="search" size={14} />
		<input placeholder="Search runs, leads, IDs…" bind:value={query} />
	</div>
</div>

<div class="lg-card" style="overflow-x:auto">
	<table>
		<thead>
			<tr><th>Run</th><th>Workflow</th><th>Status</th><th>Lead</th><th class="num">Score</th><th>Trigger</th><th class="num">Duration</th><th>Started</th><th></th></tr>
		</thead>
		<tbody>
			{#each shown as r (r.id)}
				<tr on:click={() => dispatch('open', r.workflowId)}>
					<td><code>{r.id}</code></td>
					<td style="font-weight:600">{r.workflowName}</td>
					<td>
						{#if r.status === 'success'}
							<span class="lg-pill green"><LGIcon name="checkCircle" size={12} /> Success</span>
						{:else}
							<span class="lg-pill red"><LGIcon name="xCircle" size={12} /> Failed</span>
						{/if}
					</td>
					<td class="muted">{r.lead}</td>
					<td class="num">
						{#if r.score !== null}
							<span class="score" class:hot={r.score >= 80} class:warm={r.score >= 50 && r.score < 80}>{r.score}</span>
						{:else}<span class="lg-hint">—</span>{/if}
					</td>
					<td class="muted">{r.trigger}</td>
					<td class="num muted">{fmt(r.durationMs)}</td>
					<td class="muted">{r.startedAt}</td>
					<td><LGIcon name="chevronRight" size={14} /></td>
				</tr>
			{:else}
				<tr><td colspan="9" style="text-align:center;color:#64748b;padding:32px">No runs found.</td></tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.summary {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 12px;
		margin-bottom: 16px;
	}
	.sm-card {
		padding: 12px 16px;
		display: flex;
		flex-direction: column;
	}
	.sm-card b {
		font-size: 20px;
		letter-spacing: -0.02em;
	}
	.controls {
		display: flex;
		gap: 10px;
		align-items: center;
		margin-bottom: 12px;
		flex-wrap: wrap;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 900px;
	}
	th {
		text-align: left;
		font-size: 11.5px;
		font-weight: 600;
		color: #64748b;
		padding: 10px 14px;
		background: #f8fafc;
		border-bottom: 1px solid #e6e9f0;
	}
	td {
		padding: 11px 14px;
		border-bottom: 1px solid #eef1f5;
		color: #94a3b8;
	}
	td:nth-child(2) {
		color: #0f172a;
	}
	tbody tr {
		cursor: pointer;
	}
	tbody tr:hover {
		background: #f8faff;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.muted {
		color: #475569;
	}
	code {
		font-size: 11.5px;
		color: #475569;
		background: #f1f5f9;
		padding: 1px 6px;
		border-radius: 5px;
	}
	.score {
		display: inline-block;
		min-width: 32px;
		text-align: center;
		font-weight: 700;
		font-size: 12px;
		padding: 1px 6px;
		border-radius: 6px;
		background: #f1f5f9;
		color: #475569;
	}
	.score.hot {
		background: #dcfce7;
		color: #15803d;
	}
	.score.warm {
		background: #fef3c7;
		color: #b45309;
	}
	@media (max-width: 800px) {
		.summary {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
</style>
