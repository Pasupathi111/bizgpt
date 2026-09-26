<script lang="ts">
	// Small static preview of a workflow graph for template / list cards.
	import { toneOf } from '../data/catalog';
	import { NODE_H, NODE_W, bounds, edgeGeom, inPoint, outPoint } from '../engine/geometry';
	import type { WFEdge, WFNode } from '../types';

	export let nodes: WFNode[];
	export let edges: WFEdge[];
	export let height = 120;

	$: b = bounds(nodes);
	$: pad = 30;
	$: vb = `${b.minX - pad} ${b.minY - pad} ${b.maxX - b.minX + pad * 2} ${b.maxY - b.minY + pad * 2}`;
	$: byId = new Map(nodes.map((n) => [n.id, n]));
</script>

<svg viewBox={vb} width="100%" {height} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
	{#each edges as e}
		{@const s = byId.get(e.from)}
		{@const t = byId.get(e.to)}
		{#if s && t}
			<path d={edgeGeom(outPoint(s, e.handle), inPoint(t), e.handle).d} fill="none" stroke={e.label === 'No' ? '#fca5a5' : e.label === 'Yes' ? '#86efac' : '#b8c2d3'} stroke-width="5" />
		{/if}
	{/each}
	{#each nodes as n}
		{@const tone = toneOf(n.kind)}
		<rect x={n.x} y={n.y} width={NODE_W} height={NODE_H} rx="16" fill={tone.bg} stroke={tone.border} stroke-width="4" />
		<rect x={n.x + 18} y={n.y + 20} width="30" height="30" rx="8" fill={tone.soft} />
		<circle cx={n.x + 33} cy={n.y + 35} r="7" fill={tone.icon} />
		<rect x={n.x + 60} y={n.y + 26} width={NODE_W - 90} height="14" rx="7" fill="#334155" opacity="0.55" />
		<rect x={n.x + 18} y={n.y + 64} width={NODE_W - 50} height="10" rx="5" fill="#94a3b8" opacity="0.45" />
	{/each}
</svg>
