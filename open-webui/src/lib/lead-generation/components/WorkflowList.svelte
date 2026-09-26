<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import MiniGraph from './MiniGraph.svelte';
	import { typeOf, toneOf } from '../data/catalog';
	import type { Workflow } from '../types';

	export let workflows: Workflow[];
	export let query = '';

	const dispatch = createEventDispatcher<{ open: string; toggle: string; duplicate: string; remove: string; create: void; templates: void }>();
	let filter: 'all' | 'active' | 'draft' | 'paused' = 'all';
	let view: 'list' | 'grid' = 'list';
	let menuFor: string | null = null;

	$: shown = workflows.filter(
		(w) => (filter === 'all' || w.status === filter) && (!query || `${w.name} ${w.description} ${w.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase()))
	);
	$: totalRuns = workflows.reduce((a, w) => a + w.runs, 0);
	$: totalLeads = workflows.reduce((a, w) => a + w.leads, 0);
	$: active = workflows.filter((w) => w.status === 'active').length;
	$: withRuns = workflows.filter((w) => w.runs > 0);
	$: avgSuccess = withRuns.length ? withRuns.reduce((a, w) => a + w.successRate * w.runs, 0) / withRuns.reduce((a, w) => a + w.runs, 0) : 0;

	const stats = () => [
		{ label: 'Total workflows', value: workflows.length, sub: `${active} active`, icon: 'workflow', color: '#2563eb', bg: '#eff4ff' },
		{ label: 'Leads captured (30d)', value: totalLeads.toLocaleString(), sub: '▲ 18.2% vs last month', icon: 'target', color: '#16a34a', bg: '#ecfdf3' },
		{ label: 'Executions (30d)', value: totalRuns.toLocaleString(), sub: '▲ 9.4% vs last month', icon: 'bolt', color: '#7c3aed', bg: '#f5f3ff' },
		{ label: 'Success rate', value: `${avgSuccess.toFixed(1)}%`, sub: 'Across all runs', icon: 'checkCircle', color: '#ea580c', bg: '#fff7ed' }
	];
	const count = (s: string) => (s === 'all' ? workflows.length : workflows.filter((w) => w.status === s).length);
	const triggerNode = (w: Workflow) => w.nodes.find((n) => typeOf(n.kind).category === 'trigger');
</script>

<svelte:window on:click={(e) => !(e.target instanceof Element && e.target.closest('.row-menu')) && (menuFor = null)} />

<div class="stats">
	{#each stats() as s}
		<div class="lg-card stat">
			<span class="s-icon" style="background:{s.bg};color:{s.color}"><LGIcon name={s.icon} size={18} /></span>
			<div>
				<div class="lg-hint" style="color:#64748b">{s.label}</div>
				<div class="s-val">{s.value}</div>
				<div class="s-sub" class:up={s.sub.startsWith('▲')}>{s.sub}</div>
			</div>
		</div>
	{/each}
</div>

<div class="controls">
	<div class="lg-segment">
		{#each ['all', 'active', 'draft', 'paused'] as f}
			<button class:active={filter === f} on:click={() => (filter = f)}>{f[0].toUpperCase() + f.slice(1)} <span class="lg-count">{count(f)}</span></button>
		{/each}
	</div>
	<div class="lg-search" style="width:260px;background:#fff">
		<LGIcon name="search" size={14} />
		<input placeholder="Filter workflows…" bind:value={query} />
	</div>
	<span class="lg-spacer"></span>
	<div class="lg-segment">
		<button class:active={view === 'list'} on:click={() => (view = 'list')} aria-label="List view"><LGIcon name="menu" size={14} /></button>
		<button class:active={view === 'grid'} on:click={() => (view = 'grid')} aria-label="Grid view"><LGIcon name="grid" size={14} /></button>
	</div>
	<button class="lg-btn" on:click={() => dispatch('templates')}><LGIcon name="sparkles" size={14} /> Browse templates</button>
</div>

{#if view === 'list'}
	<div class="lg-card table-wrap">
		<table>
			<thead>
				<tr>
					<th>Workflow</th>
					<th>Trigger</th>
					<th>Status</th>
					<th class="num">Runs</th>
					<th>Success</th>
					<th class="num">Leads</th>
					<th>Last run</th>
					<th>Owner</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each shown as w (w.id)}
					{@const tn = triggerNode(w)}
					<tr on:click={() => dispatch('open', w.id)}>
						<td>
							<div class="wf">
								<span class="wf-ico"><LGIcon name="workflow" size={16} /></span>
								<div style="min-width:0">
									<div class="wf-name">{w.name} <span class="ver">{w.version}</span></div>
									<div class="wf-desc">{w.description}</div>
								</div>
							</div>
						</td>
						<td>
							{#if tn}
								<span class="trig" style="background:{toneOf(tn.kind).bg};color:{toneOf(tn.kind).icon};border-color:{toneOf(tn.kind).border}">
									<LGIcon name={typeOf(tn.kind).icon} size={12} stroke={2} /> {w.trigger}
								</span>
							{/if}
						</td>
						<td>
							<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
							<div class="status" on:click|stopPropagation>
								<button class="lg-switch" class:on={w.status === 'active'} on:click={() => dispatch('toggle', w.id)} aria-label="Toggle active"></button>
								<span class="lg-pill {w.status === 'active' ? 'green' : w.status === 'paused' ? 'amber' : 'gray'}">{w.status[0].toUpperCase() + w.status.slice(1)}</span>
							</div>
						</td>
						<td class="num">{w.runs.toLocaleString()}</td>
						<td>
							{#if w.runs}
								<div class="rate"><span class="rate-bar"><span style="width:{w.successRate}%"></span></span>{w.successRate}%</div>
							{:else}<span class="lg-hint">—</span>{/if}
						</td>
						<td class="num">{w.leads.toLocaleString()}</td>
						<td class="muted">{w.lastRun}</td>
						<td><span class="lg-avatar sm" title={w.owner}>{w.owner.split(' ').map((p) => p[0]).join('')}</span></td>
						<td>
							<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
							<div class="row-menu" style="position:relative" on:click|stopPropagation>
								<button class="lg-icon-btn sm" on:click={() => (menuFor = menuFor === w.id ? null : w.id)} aria-label="Actions"><LGIcon name="dots" size={16} /></button>
								{#if menuFor === w.id}
									<div class="lg-menu">
										<button on:click={() => dispatch('open', w.id)}><LGIcon name="pencil" size={14} /> Open in editor</button>
										<button on:click={() => { menuFor = null; dispatch('duplicate', w.id); }}><LGIcon name="copy" size={14} /> Duplicate</button>
										<button on:click={() => { menuFor = null; dispatch('toggle', w.id); }}><LGIcon name={w.status === 'active' ? 'stop' : 'play'} size={14} /> {w.status === 'active' ? 'Pause' : 'Activate'}</button>
										<button style="color:#dc2626" on:click={() => { menuFor = null; dispatch('remove', w.id); }}><LGIcon name="trash" size={14} /> Delete</button>
									</div>
								{/if}
							</div>
						</td>
					</tr>
				{:else}
					<tr class="empty-row"><td colspan="9">No workflows match. <button class="link" on:click={() => dispatch('create')}>Create one</button> or <button class="link" on:click={() => dispatch('templates')}>start from a template</button>.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<div class="grid">
		{#each shown as w (w.id)}
			<button class="lg-card gcard" on:click={() => dispatch('open', w.id)}>
				<div class="preview"><MiniGraph nodes={w.nodes} edges={w.edges} height={130} /></div>
				<div class="gbody">
					<div style="display:flex;align-items:center;gap:8px">
						<span class="wf-name" style="flex:1">{w.name}</span>
						<span class="lg-pill {w.status === 'active' ? 'green' : w.status === 'paused' ? 'amber' : 'gray'}">{w.status}</span>
					</div>
					<div class="wf-desc" style="white-space:normal">{w.description}</div>
					<div class="gmeta"><span>{w.nodes.length} nodes</span><span>{w.runs.toLocaleString()} runs</span><span>{w.lastRun}</span></div>
				</div>
			</button>
		{/each}
		<button class="lg-card gcard new" on:click={() => dispatch('create')}>
			<LGIcon name="plus" size={22} />
			<div style="font-weight:600">Blank workflow</div>
			<div class="lg-hint">Start from an empty canvas</div>
		</button>
	</div>
{/if}

<style>
	.stats {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 14px;
		margin-bottom: 18px;
	}
	.stat {
		display: flex;
		gap: 12px;
		padding: 14px 16px;
		align-items: flex-start;
	}
	.s-icon {
		width: 38px;
		height: 38px;
		border-radius: 10px;
		display: grid;
		place-items: center;
		flex-shrink: 0;
	}
	.s-val {
		font-size: 22px;
		font-weight: 700;
		letter-spacing: -0.02em;
		line-height: 1.25;
	}
	.s-sub {
		font-size: 11.5px;
		color: #94a3b8;
	}
	.s-sub.up {
		color: #16a34a;
	}
	.controls {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 12px;
		flex-wrap: wrap;
	}
	.table-wrap {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 980px;
	}
	th {
		text-align: left;
		font-size: 11.5px;
		font-weight: 600;
		color: #64748b;
		padding: 10px 14px;
		background: #f8fafc;
		border-bottom: 1px solid #e6e9f0;
		white-space: nowrap;
	}
	td {
		padding: 12px 14px;
		border-bottom: 1px solid #eef1f5;
		vertical-align: middle;
	}
	tbody tr {
		cursor: pointer;
		transition: background 0.12s;
	}
	tbody tr:hover {
		background: #f8faff;
	}
	tbody tr:last-child td {
		border-bottom: 0;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.muted {
		color: #64748b;
		white-space: nowrap;
	}
	.wf {
		display: flex;
		align-items: center;
		gap: 11px;
		max-width: 380px;
	}
	.wf-ico {
		width: 34px;
		height: 34px;
		border-radius: 9px;
		background: #eff4ff;
		color: #2563eb;
		display: grid;
		place-items: center;
		flex-shrink: 0;
	}
	.wf-name {
		font-weight: 600;
		color: #0f172a;
	}
	.ver {
		font-size: 10.5px;
		color: #94a3b8;
		font-weight: 500;
		margin-left: 4px;
	}
	.wf-desc {
		font-size: 12px;
		color: #64748b;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.trig {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 11.5px;
		font-weight: 600;
		padding: 3px 8px;
		border-radius: 7px;
		border: 1px solid;
		white-space: nowrap;
	}
	.status {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.rate {
		white-space: nowrap;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		font-variant-numeric: tabular-nums;
	}
	.rate-bar {
		width: 60px;
		height: 6px;
		border-radius: 999px;
		background: #eef1f5;
		overflow: hidden;
	}
	.rate-bar span {
		display: block;
		height: 100%;
		background: linear-gradient(90deg, #22c55e, #16a34a);
	}
	.empty-row td {
		text-align: center;
		color: #64748b;
		padding: 36px;
		cursor: default;
	}
	.link {
		color: #2563eb !important;
		font-weight: 600;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
		gap: 14px;
	}
	.gcard {
		text-align: left;
		overflow: hidden;
		transition: box-shadow 0.15s, transform 0.15s, border-color 0.15s;
		display: flex !important;
		flex-direction: column;
	}
	.gcard:hover {
		border-color: #c7d6fb;
		box-shadow: 0 8px 24px -10px rgba(37, 99, 235, 0.3);
		transform: translateY(-1px);
	}
	.preview {
		background: #f8fafc radial-gradient(circle, #dfe4ec 1px, transparent 1.2px) 0 0 / 14px 14px;
		border-bottom: 1px solid #eef1f5;
		padding: 8px;
	}
	.gbody {
		padding: 12px 14px 14px;
		display: flex;
		flex-direction: column;
		gap: 5px;
	}
	.gmeta {
		display: flex;
		gap: 12px;
		font-size: 11.5px;
		color: #94a3b8;
		margin-top: 4px;
	}
	.gcard.new {
		align-items: center;
		justify-content: center;
		gap: 6px;
		min-height: 230px;
		border-style: dashed;
		color: #475569;
	}
	@media (max-width: 1100px) {
		.stats {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	@media (max-width: 560px) {
		.stats {
			grid-template-columns: 1fr;
		}
	}
</style>
