<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import MiniGraph from './MiniGraph.svelte';
	import { TONES, typeOf } from '../data/catalog';
	import { TEMPLATES, type Template } from '../data/workflows';

	export let query = '';
	const dispatch = createEventDispatcher<{ use: string }>();

	let category = 'All';
	let preview: Template | null = null;
	$: categories = ['All', ...new Set(TEMPLATES.map((t) => t.category))];
	$: shown = TEMPLATES.filter(
		(t) => (category === 'All' || t.category === category) && (!query || `${t.name} ${t.description}`.toLowerCase().includes(query.toLowerCase()))
	);
	const kinds = (t: Template) => [...new Set(t.workflow.nodes.map((n) => n.kind))].slice(0, 6);
</script>

<div class="hero lg-card">
	<div>
		<div class="eyebrow"><LGIcon name="sparkles" size={13} /> Lead generation templates</div>
		<h2>Launch a proven lead workflow in minutes</h2>
		<p>Every template is pre-wired with triggers, AI qualification, scoring, CRM and email steps. Pick one, tweak the nodes, and publish.</p>
	</div>
	<div class="hero-art"><MiniGraph nodes={TEMPLATES[0].workflow.nodes} edges={TEMPLATES[0].workflow.edges} height={150} /></div>
</div>

<div class="cats">
	{#each categories as c}
		<button class="cat" class:active={category === c} on:click={() => (category = c)}>{c}</button>
	{/each}
</div>

<div class="grid">
	{#each shown as t (t.id)}
		<div class="lg-card card">
			<button class="preview" on:click={() => (preview = t)} title="Preview">
				<MiniGraph nodes={t.workflow.nodes} edges={t.workflow.edges} height={128} />
				{#if t.popular}<span class="popular">★ Popular</span>{/if}
			</button>
			<div class="cbody">
				<div class="cat-tag">{t.category}</div>
				<div class="cname">{t.name}</div>
				<div class="cdesc">{t.description}</div>
				<div class="kinds">
					{#each kinds(t) as k}
						{@const tp = typeOf(k)}
						<span class="kind" title={tp.label} style="background:{TONES[tp.tone].soft};color:{TONES[tp.tone].icon}"><LGIcon name={tp.icon} size={12} stroke={2} /></span>
					{/each}
					<span class="lg-hint" style="margin-left:4px">{t.workflow.nodes.length} steps</span>
				</div>
				<div class="cfoot">
					<span class="lg-hint"><LGIcon name="users" size={12} /> {t.uses} uses · ~{t.minutes} min setup</span>
					<span class="lg-spacer"></span>
					<button class="lg-btn sm" on:click={() => (preview = t)}>Preview</button>
					<button class="lg-btn sm primary" on:click={() => dispatch('use', t.id)}>Use template</button>
				</div>
			</div>
		</div>
	{:else}
		<div class="lg-hint">No templates match “{query}”.</div>
	{/each}
</div>

{#if preview}
	<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
	<div class="overlay" on:click|self={() => (preview = null)}>
		<div class="modal lg-card" role="dialog" aria-label={preview.name}>
			<div class="mhead">
				<div>
					<div class="cat-tag">{preview.category}</div>
					<div class="cname" style="font-size:17px">{preview.name}</div>
				</div>
				<button class="lg-icon-btn" on:click={() => (preview = null)} aria-label="Close"><LGIcon name="x" size={18} /></button>
			</div>
			<div class="mprev"><MiniGraph nodes={preview.workflow.nodes} edges={preview.workflow.edges} height={280} /></div>
			<div class="msteps">
				{#each preview.workflow.nodes as n, i}
					{@const tp = typeOf(n.kind)}
					<div class="mstep">
						<span class="kind" style="background:{TONES[tp.tone].soft};color:{TONES[tp.tone].icon}"><LGIcon name={tp.icon} size={12} stroke={2} /></span>
						<b>{i + 1}. {n.title}</b><span class="lg-hint">— {n.desc}</span>
					</div>
				{/each}
			</div>
			<div class="mfoot">
				<span class="lg-hint">{preview.description}</span>
				<span class="lg-spacer"></span>
				<button class="lg-btn" on:click={() => (preview = null)}>Close</button>
				<button class="lg-btn primary" on:click={() => { const id = preview?.id; preview = null; id && dispatch('use', id); }}><LGIcon name="plus" size={14} /> Use this template</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.hero {
		display: grid;
		grid-template-columns: 1.1fr 1fr;
		gap: 20px;
		align-items: center;
		padding: 20px 24px;
		margin-bottom: 16px;
		background: linear-gradient(120deg, #f4f7ff 0%, #ffffff 60%);
	}
	.eyebrow {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 11.5px;
		font-weight: 700;
		color: #2563eb;
		background: #e8efff;
		padding: 3px 10px;
		border-radius: 999px;
	}
	h2 {
		font-size: 19px;
		margin: 10px 0 6px;
		letter-spacing: -0.015em;
	}
	p {
		margin: 0;
		color: #64748b;
		max-width: 520px;
	}
	.hero-art {
		background: #f8fafc radial-gradient(circle, #dfe4ec 1px, transparent 1.2px) 0 0 / 14px 14px;
		border: 1px solid #e6e9f0;
		border-radius: 10px;
		padding: 8px;
	}
	.cats {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin-bottom: 14px;
	}
	.cat {
		padding: 5px 12px !important;
		border-radius: 999px;
		border: 1px solid #e2e8f0 !important;
		background: #fff !important;
		color: #475569;
		font-weight: 500;
		font-size: 12.5px;
	}
	.cat.active {
		background: #0f172a !important;
		border-color: #0f172a !important;
		color: #fff;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 14px;
	}
	.card {
		overflow: hidden;
		display: flex;
		flex-direction: column;
		transition: box-shadow 0.15s, border-color 0.15s;
	}
	.card:hover {
		border-color: #c7d6fb;
		box-shadow: 0 8px 24px -12px rgba(37, 99, 235, 0.35);
	}
	.preview {
		position: relative;
		display: block;
		width: 100%;
		background: #f8fafc radial-gradient(circle, #dfe4ec 1px, transparent 1.2px) 0 0 / 14px 14px !important;
		border-bottom: 1px solid #eef1f5 !important;
		padding: 8px !important;
	}
	.popular {
		position: absolute;
		top: 8px;
		left: 8px;
		font-size: 10.5px;
		font-weight: 700;
		color: #b45309;
		background: #fef3c7;
		border: 1px solid #fde68a;
		padding: 1px 8px;
		border-radius: 999px;
	}
	.cbody {
		padding: 12px 14px 14px;
		display: flex;
		flex-direction: column;
		gap: 5px;
		flex: 1;
	}
	.cat-tag {
		font-size: 10.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #7c3aed;
	}
	.cname {
		font-weight: 700;
		font-size: 14px;
	}
	.cdesc {
		color: #64748b;
		font-size: 12.5px;
		flex: 1;
	}
	.kinds {
		display: flex;
		align-items: center;
		gap: 4px;
		margin-top: 4px;
	}
	.kind {
		width: 22px;
		height: 22px;
		border-radius: 6px;
		display: inline-grid;
		place-items: center;
		flex-shrink: 0;
	}
	.cfoot {
		display: flex;
		align-items: center;
		gap: 6px;
		margin-top: 8px;
		padding-top: 10px;
		border-top: 1px solid #eef1f5;
	}
	.cfoot .lg-hint {
		display: inline-flex;
		align-items: center;
		gap: 4px;
	}
	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(15, 23, 42, 0.45);
		display: grid;
		place-items: center;
		z-index: 80;
		padding: 16px;
		animation: fade 0.15s ease;
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}
	.modal {
		width: min(820px, 100%);
		max-height: 90vh;
		overflow: auto;
		padding: 18px 20px;
	}
	.mhead {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 12px;
	}
	.mprev {
		background: #f8fafc radial-gradient(circle, #dfe4ec 1px, transparent 1.2px) 0 0 / 16px 16px;
		border: 1px solid #e6e9f0;
		border-radius: 10px;
		padding: 12px;
	}
	.msteps {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 6px 16px;
		margin: 14px 0;
	}
	.mstep {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 12.5px;
		min-width: 0;
	}
	.mstep .lg-hint {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.mfoot {
		display: flex;
		align-items: center;
		gap: 8px;
		padding-top: 12px;
		border-top: 1px solid #eef1f5;
	}
	@media (max-width: 800px) {
		.hero {
			grid-template-columns: 1fr;
		}
		.msteps {
			grid-template-columns: 1fr;
		}
	}
</style>
