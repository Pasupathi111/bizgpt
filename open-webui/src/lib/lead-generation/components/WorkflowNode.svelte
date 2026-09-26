<script lang="ts">
	import LGIcon from './LGIcon.svelte';
	import { toneOf, typeOf } from '../data/catalog';
	import { NODE_H, NODE_W } from '../engine/geometry';
	import type { NodeStatus, WFNode } from '../types';

	export let node: WFNode;
	export let index: number;
	export let selected = false;
	export let status: NodeStatus = 'idle';
	export let ms: number | null = null;
	/** a connection drag is in progress and this node is a valid drop target */
	export let droppable = false;

	$: type = typeOf(node.kind);
	$: tone = toneOf(node.kind);
	$: isTrigger = type.category === 'trigger';
</script>

<div
	class="lg-node {status}"
	class:selected
	class:droppable
	data-node-id={node.id}
	style="left:{node.x}px;top:{node.y}px;width:{NODE_W}px;height:{NODE_H}px;--t-bg:{tone.bg};--t-border:{tone.border};--t-icon:{tone.icon};--t-soft:{tone.soft}"
	role="button"
	tabindex="-1"
	aria-label="{index}. {node.title}"
>
	{#if !isTrigger}
		<span class="lg-handle in" data-handle="in" data-node-id={node.id} title="Input"></span>
	{/if}

	<div class="head">
		<span class="head-icon"><LGIcon name={isTrigger ? 'bolt' : type.icon} size={15} stroke={2} /></span>
		<span class="title">{index}. {node.title}</span>
		{#if status === 'running'}
			<span class="state spin" title="Running"></span>
		{:else if status === 'success'}
			<span class="state ok" title="Succeeded"><LGIcon name="check" size={11} stroke={3} /></span>
		{:else if status === 'error'}
			<span class="state err" title="Failed"><LGIcon name="x" size={11} stroke={3} /></span>
		{/if}
	</div>
	<div class="sub">
		<span class="sub-icon"><LGIcon name={type.icon} size={12} stroke={2} /></span>
		<span class="sub-text">{node.subtitle}</span>
	</div>
	<div class="desc">{node.desc}</div>

	{#if status === 'success' && ms !== null}
		<span class="ms">{ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`}</span>
	{/if}

	{#if type.branching}
		<span class="lg-handle out yes" data-handle="true" data-node-id={node.id} title="Yes"></span>
		<span class="lg-handle out no" data-handle="false" data-node-id={node.id} title="No"></span>
	{:else}
		<span class="lg-handle out" data-handle="out" data-node-id={node.id} title="Drag to connect"></span>
	{/if}
</div>

<style>
	.lg-node {
		position: absolute;
		border-radius: 12px;
		background: var(--t-bg);
		border: 1.5px solid var(--t-border);
		padding: 11px 13px 10px;
		box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05), 0 2px 6px rgba(15, 23, 42, 0.04);
		cursor: grab;
		user-select: none;
		transition: box-shadow 0.15s, border-color 0.15s, opacity 0.25s, transform 0.15s;
		display: flex;
		flex-direction: column;
		gap: 5px;
	}
	.lg-node:hover {
		box-shadow: 0 4px 16px -4px rgba(15, 23, 42, 0.18);
	}
	.lg-node.selected {
		border-color: #2563eb;
		box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18), 0 6px 18px -6px rgba(37, 99, 235, 0.35);
	}
	.lg-node.running {
		border-color: #3b82f6;
		animation: lg-pulse 1.1s ease-in-out infinite;
	}
	.lg-node.success {
		border-color: #4ade80;
	}
	.lg-node.error {
		border-color: #f87171;
	}
	.lg-node.skipped {
		opacity: 0.42;
		filter: grayscale(0.5);
	}
	.lg-node.droppable {
		box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
	}
	@keyframes lg-pulse {
		0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.35); }
		50% { box-shadow: 0 0 0 7px rgba(59, 130, 246, 0); }
	}
	.head {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.head-icon {
		color: var(--t-icon);
		display: flex;
	}
	.title {
		font-weight: 700;
		font-size: 13px;
		color: #0f172a;
		flex: 1;
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.state {
		width: 18px;
		height: 18px;
		border-radius: 999px;
		display: grid;
		place-items: center;
		color: #fff;
		flex-shrink: 0;
	}
	.state.ok { background: #22c55e; }
	.state.err { background: #ef4444; }
	.state.spin {
		border: 2px solid #bfdbfe;
		border-top-color: #2563eb;
		animation: lg-spin 0.7s linear infinite;
	}
	@keyframes lg-spin { to { transform: rotate(360deg); } }
	.sub {
		display: flex;
		align-items: center;
		gap: 7px;
		padding-left: 1px;
	}
	.sub-icon {
		width: 20px;
		height: 20px;
		border-radius: 6px;
		display: grid;
		place-items: center;
		background: var(--t-soft);
		color: var(--t-icon);
		flex-shrink: 0;
	}
	.sub-text {
		font-weight: 600;
		font-size: 12.5px;
		color: #1e293b;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.desc {
		font-size: 11.5px;
		color: #64748b;
		line-height: 1.35;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.ms {
		white-space: nowrap;
		position: absolute;
		right: 8px;
		bottom: -19px;
		font-size: 10.5px;
		color: #16a34a;
		font-weight: 600;
		font-family: ui-monospace, Menlo, monospace;
	}
	.lg-handle {
		position: absolute;
		width: 12px;
		height: 12px;
		border-radius: 999px;
		background: #fff;
		border: 2px solid #94a3b8;
		z-index: 2;
		transition: transform 0.12s, border-color 0.12s, background 0.12s;
	}
	.lg-handle.in {
		left: -7px;
		top: calc(50% - 6px);
	}
	.lg-handle.out {
		right: -7px;
		top: calc(50% - 6px);
		cursor: crosshair;
	}
	.lg-handle.out.no {
		right: auto;
		left: calc(50% - 6px);
		top: auto;
		bottom: -7px;
		border-color: #f87171;
	}
	.lg-handle.out.yes {
		border-color: #22c55e;
	}
	.lg-handle:hover,
	.lg-node.droppable .lg-handle.in {
		transform: scale(1.35);
		border-color: #2563eb;
		background: #eff6ff;
	}
</style>
