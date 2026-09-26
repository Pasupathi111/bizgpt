<script lang="ts">
	import { createEventDispatcher, onDestroy, onMount, tick } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import WorkflowNode from './WorkflowNode.svelte';
	import { typeOf, toneOf } from '../data/catalog';
	import { NODE_H, NODE_W, bounds, edgeGeom, inPoint, outPoint } from '../engine/geometry';
	import type { EdgeStatus, Handle, NodeStatus, WFEdge, WFNode } from '../types';

	export let nodes: WFNode[];
	export let edges: WFEdge[];
	export let selectedNodeId: string | null = null;
	export let selectedEdgeId: string | null = null;
	export let nodeStatus: Record<string, NodeStatus> = {};
	export let edgeStatus: Record<string, EdgeStatus> = {};
	export let nodeMs: Record<string, number> = {};

	const dispatch = createEventDispatcher<{
		change: void;
		drop: { kind: string; x: number; y: number };
		connected: { from: string; to: string };
	}>();

	let el: HTMLDivElement;
	let width = 800;
	let height = 500;
	let tx = 40;
	let ty = 40;
	let k = 1;
	let showMinimap = true;
	let animateView = false;
	// edges are drawn in a large fixed SVG so hit-testing never depends on overflow
	const SVG_SPAN = 20000;

	type Drag =
		| { type: 'node'; id: string; sx: number; sy: number; ox: number; oy: number; moved: boolean }
		| { type: 'pan'; sx: number; sy: number; ox: number; oy: number };
	let drag: Drag | null = null;
	let connecting: { from: string; handle: Handle; x: number; y: number; over: string | null } | null = null;

	$: byId = new Map(nodes.map((n) => [n.id, n]));
	$: edgeList = edges
		.map((e) => {
			const s = byId.get(e.from);
			const t = byId.get(e.to);
			if (!s || !t) return null;
			return { edge: e, g: edgeGeom(outPoint(s, e.handle), inPoint(t), e.handle) };
		})
		.filter(Boolean) as { edge: WFEdge; g: ReturnType<typeof edgeGeom> }[];

	$: tempPath = (() => {
		if (!connecting) return '';
		const s = byId.get(connecting.from);
		if (!s) return '';
		const target = connecting.over ? byId.get(connecting.over) : null;
		const t = target ? inPoint(target) : { x: connecting.x, y: connecting.y };
		return edgeGeom(outPoint(s, connecting.handle), t, t.x < outPoint(s, connecting.handle).x + 30 && connecting.handle !== 'false' ? 'out' : connecting.handle).d;
	})();

	const toCanvas = (cx: number, cy: number) => {
		const r = el.getBoundingClientRect();
		return { x: (cx - r.left - tx) / k, y: (cy - r.top - ty) / k };
	};

	function onPointerDown(e: PointerEvent) {
		if (e.button !== 0) return;
		const target = e.target as HTMLElement;
		if (target.closest('.lg-canvas-ui')) return;

		const handleEl = target.closest('[data-handle]') as HTMLElement | null;
		if (handleEl && handleEl.dataset.handle !== 'in') {
			const p = toCanvas(e.clientX, e.clientY);
			connecting = { from: handleEl.dataset.nodeId!, handle: handleEl.dataset.handle as Handle, x: p.x, y: p.y, over: null };
			e.preventDefault();
			return;
		}

		if (target.closest('[data-edge-id]')) {
			selectedEdgeId = (target.closest('[data-edge-id]') as HTMLElement).dataset.edgeId!;
			selectedNodeId = null;
			return;
		}

		const nodeEl = target.closest('.lg-node') as HTMLElement | null;
		if (nodeEl) {
			const n = byId.get(nodeEl.dataset.nodeId!);
			if (!n) return;
			drag = { type: 'node', id: n.id, sx: e.clientX, sy: e.clientY, ox: n.x, oy: n.y, moved: false };
			selectedNodeId = n.id;
			selectedEdgeId = null;
			return;
		}

		drag = { type: 'pan', sx: e.clientX, sy: e.clientY, ox: tx, oy: ty };
		selectedNodeId = null;
		selectedEdgeId = null;
	}

	function onPointerMove(e: PointerEvent) {
		if (connecting) {
			const p = toCanvas(e.clientX, e.clientY);
			const over = (document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null)?.closest('.lg-node') as HTMLElement | null;
			const overId = over?.dataset.nodeId ?? null;
			const valid = overId && overId !== connecting.from && typeOf(byId.get(overId)!.kind).category !== 'trigger';
			connecting = { ...connecting, x: p.x, y: p.y, over: valid ? overId : null };
			return;
		}
		if (!drag) return;
		if (drag.type === 'pan') {
			tx = drag.ox + (e.clientX - drag.sx);
			ty = drag.oy + (e.clientY - drag.sy);
		} else {
			const dx = (e.clientX - drag.sx) / k;
			const dy = (e.clientY - drag.sy) / k;
			if (!drag.moved && Math.hypot(dx, dy) < 3) return;
			drag.moved = true;
			const n = byId.get(drag.id);
			if (n) {
				// snap to a 10px grid, like n8n
				n.x = Math.round((drag.ox + dx) / 10) * 10;
				n.y = Math.round((drag.oy + dy) / 10) * 10;
				nodes = nodes;
			}
		}
	}

	function onPointerUp() {
		if (connecting) {
			const { from, handle, over } = connecting;
			connecting = null;
			if (over && !edges.some((e) => e.from === from && e.to === over && e.handle === handle)) {
				// a branch handle carries one path; replace an existing one
				if (handle !== 'out') edges = edges.filter((e) => !(e.from === from && e.handle === handle));
				edges = [...edges, { id: `${from}-${over}-${Date.now().toString(36)}`, from, to: over, handle, label: handle === 'true' ? 'Yes' : handle === 'false' ? 'No' : undefined }];
				dispatch('connected', { from, to: over });
				dispatch('change');
			}
			return;
		}
		if (drag?.type === 'node' && drag.moved) dispatch('change');
		drag = null;
	}

	function onWheel(e: WheelEvent) {
		e.preventDefault();
		if (e.ctrlKey || e.metaKey) {
			const r = el.getBoundingClientRect();
			zoomAt(e.clientX - r.left, e.clientY - r.top, k * Math.exp(-e.deltaY * 0.0022));
		} else {
			tx -= e.deltaX;
			ty -= e.deltaY;
		}
	}

	function zoomAt(mx: number, my: number, next: number) {
		const nk = Math.min(2, Math.max(0.3, next));
		tx = mx - ((mx - tx) * nk) / k;
		ty = my - ((my - ty) * nk) / k;
		k = nk;
	}

	async function smooth(fn: () => void) {
		animateView = true;
		fn();
		await new Promise((r) => setTimeout(r, 260));
		animateView = false;
	}

	export const zoomIn = () => smooth(() => zoomAt(width / 2, height / 2, k * 1.2));
	export const zoomOut = () => smooth(() => zoomAt(width / 2, height / 2, k / 1.2));
	export function fitView(animated = true) {
		const r = el?.getBoundingClientRect();
		if (r?.width) width = r.width;
		if (r?.height) height = r.height;
		const b = bounds(nodes);
		const pad = 48;
		const bw = b.maxX - b.minX;
		const bh = b.maxY - b.minY + 30;
		// keep cards readable: never shrink below 72%, pan instead (like n8n)
		const nk = Math.min(1, Math.max(0.72, Math.min((width - pad * 2) / bw, (height - pad * 2) / bh)));
		const apply = () => {
			k = nk;
			tx = bw * nk + pad * 2 <= width ? (width - bw * nk) / 2 - b.minX * nk : pad - b.minX * nk;
			ty = bh * nk + pad * 2 <= height ? (height - bh * nk) / 2 - b.minY * nk : pad - b.minY * nk;
		};
		animated ? smooth(apply) : apply();
	}

	export function centerOn(id: string) {
		const n = byId.get(id);
		if (!n) return;
		smooth(() => {
			tx = width / 2 - (n.x + NODE_W / 2) * k;
			ty = height / 2 - (n.y + NODE_H / 2) * k;
		});
	}

	/** Canvas coordinates of the visible centre, for click-to-add from the palette. */
	export const viewCenter = () => ({ x: (width / 2 - tx) / k - NODE_W / 2, y: (height / 2 - ty) / k - NODE_H / 2 });

	function onDrop(e: DragEvent) {
		const kind = e.dataTransfer?.getData('application/x-lg-node');
		if (!kind) return;
		e.preventDefault();
		const p = toCanvas(e.clientX, e.clientY);
		dispatch('drop', { kind, x: Math.round((p.x - NODE_W / 2) / 10) * 10, y: Math.round((p.y - NODE_H / 2) / 10) * 10 });
	}

	function deleteEdge(id: string) {
		edges = edges.filter((e) => e.id !== id);
		selectedEdgeId = null;
		dispatch('change');
	}

	// Minimap
	const MM_W = 176;
	const MM_H = 112;
	$: mb = bounds(nodes);
	$: mmPad = 40;
	$: mmScale = Math.min(MM_W / (mb.maxX - mb.minX + mmPad * 2), MM_H / (mb.maxY - mb.minY + mmPad * 2));
	$: mmX = (x: number) => (x - mb.minX + mmPad) * mmScale;
	$: mmY = (y: number) => (y - mb.minY + mmPad) * mmScale;

	function onMinimapClick(e: MouseEvent) {
		const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
		const cx = (e.clientX - r.left) / mmScale + mb.minX - mmPad;
		const cy = (e.clientY - r.top) / mmScale + mb.minY - mmPad;
		smooth(() => {
			tx = width / 2 - cx * k;
			ty = height / 2 - cy * k;
		});
	}

	const edgeClass = (e: WFEdge, sel: string | null, st: Record<string, EdgeStatus>) =>
		`${st[e.id] ?? 'idle'}${sel === e.id ? ' selected' : ''}`;
	const marker = (e: WFEdge, sel: string | null, st: Record<string, EdgeStatus>) =>
		sel === e.id ? 'url(#lg-arrow-sel)' : st[e.id] === 'active' ? 'url(#lg-arrow-active)' : st[e.id] === 'done' ? 'url(#lg-arrow-done)' : 'url(#lg-arrow)';

	onMount(async () => {
		window.addEventListener('pointermove', onPointerMove);
		window.addEventListener('pointerup', onPointerUp);
		await tick();
		fitView(false);
	});
	onDestroy(() => {
		if (typeof window === 'undefined') return;
		window.removeEventListener('pointermove', onPointerMove);
		window.removeEventListener('pointerup', onPointerUp);
	});
</script>

<div
	class="lg-canvas"
	class:panning={drag?.type === 'pan'}
	class:connecting={!!connecting}
	bind:this={el}
	bind:clientWidth={width}
	bind:clientHeight={height}
	on:pointerdown={onPointerDown}
	on:wheel|nonpassive={onWheel}
	on:scroll={() => el && (el.scrollLeft = el.scrollTop = 0)}
	on:dragover|preventDefault
	on:drop={onDrop}
	role="application"
	aria-label="Workflow canvas"
	style="background-size:{20 * k}px {20 * k}px;background-position:{tx}px {ty}px"
>
	<div class="viewport" class:animate={animateView} style="transform:translate({tx}px,{ty}px) scale({k})">
		<svg class="edges" width={SVG_SPAN} height={SVG_SPAN} viewBox="{-SVG_SPAN / 2} {-SVG_SPAN / 2} {SVG_SPAN} {SVG_SPAN}" style="left:{-SVG_SPAN / 2}px;top:{-SVG_SPAN / 2}px">
			<defs>
				{#each [['lg-arrow', '#94a3b8'], ['lg-arrow-active', '#2563eb'], ['lg-arrow-done', '#3b82f6'], ['lg-arrow-sel', '#2563eb']] as [id, color]}
					<marker {id} viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
						<path d="M0,0 L10,5 L0,10 z" fill={color} />
					</marker>
				{/each}
			</defs>
			{#each edgeList as { edge, g } (edge.id)}
				<path class="edge-hit" data-edge-id={edge.id} d={g.d} />
				<path class="edge {edgeClass(edge, selectedEdgeId, edgeStatus)}" d={g.d} marker-end={marker(edge, selectedEdgeId, edgeStatus)} />
			{/each}
			{#if connecting}
				<path class="edge temp" d={tempPath} marker-end="url(#lg-arrow-active)" />
			{/if}
		</svg>

		{#each edgeList as { edge, g } (edge.id)}
			{#if edge.label}
				<span
					class="edge-label {edge.label === 'Yes' ? 'yes' : edge.label === 'No' ? 'no' : 'route'}"
					class:dim={edgeStatus[edge.id] === 'skipped'}
					style="left:{g.lx}px;top:{g.ly}px"
					data-edge-id={edge.id}>{edge.label}</span
				>
			{/if}
			{#if selectedEdgeId === edge.id}
				<button
					class="edge-del lg-canvas-ui"
					style="left:{g.lx}px;top:{g.ly + (edge.label ? 24 : 0)}px"
					on:click={() => deleteEdge(edge.id)}
					title="Delete connection (Del)"
				>
					<LGIcon name="trash" size={13} />
				</button>
			{/if}
		{/each}

		{#each nodes as node, i (node.id)}
			<WorkflowNode
				{node}
				index={i + 1}
				selected={selectedNodeId === node.id}
				status={nodeStatus[node.id] ?? 'idle'}
				ms={nodeMs[node.id] ?? null}
				droppable={connecting?.over === node.id}
			/>
		{/each}
	</div>

	{#if !nodes.length}
		<div class="empty">
			<div class="empty-icon"><LGIcon name="plus" size={22} /></div>
			<div style="font-weight:600;color:#1e293b">Add your first step</div>
			<div class="lg-hint">Drag a trigger from the left panel onto the canvas</div>
		</div>
	{/if}

	<div class="toolbar lg-canvas-ui">
		<button class="lg-icon-btn sm" on:click={zoomOut} title="Zoom out"><LGIcon name="minus" size={15} /></button>
		<button class="zoom" on:click={() => smooth(() => zoomAt(width / 2, height / 2, 1))} title="Reset to 100%">{Math.round(k * 100)}%</button>
		<button class="lg-icon-btn sm" on:click={zoomIn} title="Zoom in"><LGIcon name="plus" size={15} /></button>
		<span class="sep"></span>
		<button class="lg-icon-btn sm" on:click={() => fitView()} title="Fit to view"><LGIcon name="expand" size={15} /></button>
		<button class="lg-icon-btn sm" class:on={showMinimap} on:click={() => (showMinimap = !showMinimap)} title="Toggle minimap"><LGIcon name="map" size={15} /></button>
	</div>

	<div class="hint lg-canvas-ui lg-hide-sm">
		<span><b>Drag</b> ● to connect</span>
		<span><b>Del</b> remove</span>
		<span><b>Ctrl + scroll</b> zoom</span>
	</div>

	{#if showMinimap && nodes.length}
		<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
		<div class="minimap lg-canvas-ui" style="width:{MM_W}px;height:{MM_H}px" on:click={onMinimapClick}>
			<svg width={MM_W} height={MM_H}>
				{#each edgeList as { edge }}
					{@const s = byId.get(edge.from)}
					{@const t = byId.get(edge.to)}
					{#if s && t}
						<line x1={mmX(s.x + NODE_W)} y1={mmY(s.y + NODE_H / 2)} x2={mmX(t.x)} y2={mmY(t.y + NODE_H / 2)} stroke="#cbd5e1" stroke-width="1" />
					{/if}
				{/each}
				{#each nodes as n (n.id)}
					<rect x={mmX(n.x)} y={mmY(n.y)} width={NODE_W * mmScale} height={NODE_H * mmScale} rx="2" fill={toneOf(n.kind).soft} stroke={nodeStatus[n.id] === 'success' ? '#22c55e' : toneOf(n.kind).icon} stroke-width="0.8" />
				{/each}
				<rect class="mm-view" x={mmX(-tx / k)} y={mmY(-ty / k)} width={(width / k) * mmScale} height={(height / k) * mmScale} />
			</svg>
		</div>
	{/if}
</div>

<style>
	.lg-canvas {
		position: relative;
		flex: 1;
		min-width: 0;
		overflow: hidden;
		background-color: #f8fafc;
		background-image: radial-gradient(circle, #cfd6e2 1px, transparent 1.2px);
		cursor: default;
		touch-action: none;
	}
	.lg-canvas.panning {
		cursor: grabbing;
	}
	.lg-canvas.connecting {
		cursor: crosshair;
	}
	.viewport {
		position: absolute;
		left: 0;
		top: 0;
		transform-origin: 0 0;
	}
	.viewport.animate {
		transition: transform 0.25s ease;
	}
	.edges {
		position: absolute;
		overflow: visible;
		pointer-events: none;
	}
	.edge {
		fill: none;
		stroke: #94a3b8;
		stroke-width: 2;
		transition: stroke 0.2s, opacity 0.2s;
	}
	.edge.active {
		stroke: #2563eb;
		stroke-width: 2.5;
		stroke-dasharray: 7 6;
		animation: lg-flow 0.5s linear infinite;
	}
	.edge.done {
		stroke: #3b82f6;
		stroke-width: 2.25;
	}
	.edge.skipped {
		stroke-dasharray: 4 5;
		opacity: 0.45;
	}
	.edge.selected {
		stroke: #2563eb;
		stroke-width: 3;
	}
	.edge.temp {
		stroke: #2563eb;
		stroke-dasharray: 6 5;
		animation: lg-flow 0.5s linear infinite;
	}
	@keyframes lg-flow {
		to {
			stroke-dashoffset: -13;
		}
	}
	.edge-hit {
		fill: none;
		stroke: transparent;
		stroke-width: 16;
		pointer-events: stroke;
		cursor: pointer;
	}
	.edge-hit:hover + .edge:not(.selected) {
		stroke: #64748b;
	}
	.edge-label {
		white-space: nowrap;
		position: absolute;
		transform: translate(-50%, -50%);
		font-size: 11px;
		font-weight: 700;
		padding: 2px 10px;
		border-radius: 999px;
		color: #fff;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
		cursor: pointer;
		z-index: 1;
		transition: opacity 0.2s;
	}
	.edge-label.yes {
		background: #22c55e;
	}
	.edge-label.no {
		background: #f87171;
	}
	.edge-label.route {
		background: #fff;
		color: #a21caf;
		border: 1px solid #f5d0fe;
	}
	.edge-label.dim {
		opacity: 0.45;
	}
	.edge-del {
		position: absolute;
		transform: translate(-50%, -50%);
		width: 26px;
		height: 26px;
		border-radius: 999px;
		background: #fff !important;
		color: #ef4444 !important;
		border: 1px solid #fecaca !important;
		display: grid;
		place-items: center;
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
		z-index: 3;
	}
	.toolbar {
		position: absolute;
		top: 12px;
		right: 12px;
		display: flex;
		align-items: center;
		gap: 2px;
		background: #fff;
		border: 1px solid #e6e9f0;
		border-radius: 10px;
		padding: 3px;
		box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
	}
	.toolbar .zoom {
		min-width: 46px;
		font-size: 12px;
		font-weight: 600;
		color: #334155;
		padding: 4px 2px;
		border-radius: 6px;
	}
	.toolbar .zoom:hover {
		background: #f1f4f9;
	}
	.toolbar .sep {
		width: 1px;
		height: 18px;
		background: #e2e8f0;
		margin: 0 3px;
	}
	.toolbar :global(.on) {
		color: #2563eb;
		background: #eff4ff;
	}
	.hint {
		position: absolute;
		left: 12px;
		bottom: 12px;
		display: flex;
		gap: 12px;
		font-size: 11px;
		color: #64748b;
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e6e9f0;
		border-radius: 8px;
		padding: 5px 10px;
	}
	.hint b {
		color: #334155;
		font-weight: 600;
	}
	.minimap {
		position: absolute;
		right: 12px;
		bottom: 12px;
		background: rgba(255, 255, 255, 0.95);
		border: 1px solid #e6e9f0;
		border-radius: 10px;
		box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
		overflow: hidden;
		cursor: pointer;
	}
	.mm-view {
		fill: rgba(37, 99, 235, 0.06);
		stroke: #2563eb;
		stroke-width: 1;
	}
	.empty {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 6px;
		pointer-events: none;
	}
	.empty-icon {
		width: 52px;
		height: 52px;
		border-radius: 14px;
		border: 2px dashed #cbd5e1;
		display: grid;
		place-items: center;
		color: #94a3b8;
		margin-bottom: 4px;
	}
</style>
