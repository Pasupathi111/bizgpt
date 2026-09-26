<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import { CATEGORIES, NODE_TYPES, TONES } from '../data/catalog';

	const dispatch = createEventDispatcher<{ add: string }>();
	let query = '';

	$: groups = CATEGORIES.map((c) => ({
		...c,
		items: Object.entries(NODE_TYPES).filter(
			([, t]) => t.category === c.key && (!query || `${t.label} ${t.desc}`.toLowerCase().includes(query.toLowerCase()))
		)
	})).filter((g) => g.items.length);

	function onDragStart(e: DragEvent, kind: string) {
		e.dataTransfer?.setData('application/x-lg-node', kind);
		if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy';
	}
</script>

<div class="palette">
	<div class="search">
		<LGIcon name="search" size={14} />
		<input placeholder="Search nodes..." bind:value={query} aria-label="Search nodes" />
	</div>
	<div class="groups">
		{#each groups as g (g.key)}
			<div class="group-title">{g.label}</div>
			{#each g.items as [kind, t] (kind)}
				<button
					class="item"
					draggable="true"
					on:dragstart={(e) => onDragStart(e, kind)}
					on:click={() => dispatch('add', kind)}
					title="{t.desc} — drag onto the canvas or click to add"
				>
					<span class="ico" style="background:{TONES[t.tone].soft};color:{TONES[t.tone].icon}">
						<LGIcon name={t.icon} size={13} stroke={2} />
					</span>
					<span class="lbl">{t.label}</span>
					<span class="grip"><LGIcon name="plus" size={12} /></span>
				</button>
			{/each}
		{:else}
			<div class="lg-hint" style="padding:16px 6px">No nodes match “{query}”.</div>
		{/each}
	</div>
</div>

<style>
	.palette {
		width: 212px;
		flex-shrink: 0;
		border-right: 1px solid #e6e9f0;
		display: flex;
		flex-direction: column;
		min-height: 0;
		background: #fff;
	}
	.search {
		display: flex;
		align-items: center;
		gap: 7px;
		margin: 12px 12px 6px;
		padding: 6px 10px;
		border: 1px solid #e6e9f0;
		border-radius: 8px;
		color: #94a3b8;
		background: #f8fafc;
	}
	.search input {
		border: 0;
		outline: 0;
		background: transparent;
		min-width: 0;
		flex: 1;
		font-size: 12.5px;
	}
	.groups {
		flex: 1;
		overflow-y: auto;
		padding: 0 8px 12px;
	}
	.group-title {
		font-size: 11px;
		font-weight: 700;
		color: #475569;
		padding: 12px 6px 5px;
		letter-spacing: 0.01em;
	}
	.item {
		display: flex !important;
		align-items: center;
		gap: 9px;
		width: 100%;
		padding: 6px 8px !important;
		border-radius: 8px;
		text-align: left;
		cursor: grab !important;
		border: 1px solid transparent !important;
		transition: background 0.12s, border-color 0.12s;
	}
	.item:hover {
		background: #f5f8ff !important;
		border-color: #dbe5fb !important;
	}
	.item:active {
		cursor: grabbing !important;
	}
	.ico {
		width: 22px;
		height: 22px;
		border-radius: 6px;
		display: grid;
		place-items: center;
		flex-shrink: 0;
	}
	.lbl {
		flex: 1;
		font-size: 12.5px;
		color: #1e293b;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.grip {
		color: #94a3b8;
		opacity: 0;
		display: flex;
	}
	.item:hover .grip {
		opacity: 1;
	}
</style>
