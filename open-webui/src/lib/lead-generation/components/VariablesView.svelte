<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';
	import type { Variable } from '../data/samples';

	export let variables: Variable[];
	const dispatch = createEventDispatcher<{ toast: { message: string; kind?: 'success' | 'error' | 'info' } }>();

	let adding = false;
	let draft: Variable = { key: '', value: '', type: 'string', scope: 'All workflows' };
	let revealed = new Set<string>();

	function add() {
		const key = draft.key.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
		if (!key || !draft.value) return dispatch('toast', { message: 'Key and value are required', kind: 'error' });
		if (variables.some((v) => v.key === key)) return dispatch('toast', { message: `${key} already exists`, kind: 'error' });
		variables = [...variables, { ...draft, key }];
		draft = { key: '', value: '', type: 'string', scope: 'All workflows' };
		adding = false;
		dispatch('toast', { message: `Variable ${key} added`, kind: 'success' });
	}
	function remove(key: string) {
		variables = variables.filter((v) => v.key !== key);
		dispatch('toast', { message: `Variable ${key} removed`, kind: 'info' });
	}
	function toggle(key: string) {
		revealed.has(key) ? revealed.delete(key) : revealed.add(key);
		revealed = revealed;
	}
</script>

<div class="head">
	<div>
		<div style="font-weight:700;font-size:15px">Environment variables</div>
		<div class="lg-hint">Reference in any node as <code>{'{{env.KEY}}'}</code>. Secrets are encrypted at rest and masked in logs.</div>
	</div>
	<button class="lg-btn primary" on:click={() => (adding = !adding)}><LGIcon name="plus" size={14} /> Add variable</button>
</div>

<div class="lg-card" style="overflow-x:auto">
	<table>
		<thead><tr><th>Key</th><th>Value</th><th>Type</th><th>Scope</th><th></th></tr></thead>
		<tbody>
			{#if adding}
				<tr class="draft">
					<td><input class="lg-input" placeholder="MY_VARIABLE" bind:value={draft.key} /></td>
					<td><input class="lg-input" placeholder="value" bind:value={draft.value} type={draft.type === 'secret' ? 'password' : 'text'} /></td>
					<td>
						<select class="lg-select" bind:value={draft.type}><option value="string">string</option><option value="number">number</option><option value="secret">secret</option></select>
					</td>
					<td><input class="lg-input" bind:value={draft.scope} /></td>
					<td style="white-space:nowrap">
						<button class="lg-btn sm primary" on:click={add}>Save</button>
						<button class="lg-btn sm" on:click={() => (adding = false)}>Cancel</button>
					</td>
				</tr>
			{/if}
			{#each variables as v (v.key)}
				<tr>
					<td><span class="key"><LGIcon name={v.type === 'secret' ? 'key' : 'variable'} size={13} /> {v.key}</span></td>
					<td>
						<span class="val">{v.type === 'secret' && !revealed.has(v.key) ? '••••••••••••••••' : v.value}</span>
						{#if v.type === 'secret'}
							<button class="lg-icon-btn sm" on:click={() => toggle(v.key)} title="Reveal"><LGIcon name="eye" size={14} /></button>
						{/if}
					</td>
					<td><span class="lg-pill {v.type === 'secret' ? 'red' : v.type === 'number' ? 'blue' : 'gray'}">{v.type}</span></td>
					<td class="muted">{v.scope}</td>
					<td><button class="lg-icon-btn sm" on:click={() => remove(v.key)} title="Delete"><LGIcon name="trash" size={14} /></button></td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
		margin-bottom: 14px;
	}
	code {
		font-size: 11.5px;
		background: #f1f5f9;
		padding: 1px 5px;
		border-radius: 4px;
		color: #7c3aed;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 760px;
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
		padding: 10px 14px;
		border-bottom: 1px solid #eef1f5;
	}
	td:nth-child(2) {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.draft td {
		background: #f8faff;
	}
	.key {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		font-family: ui-monospace, Menlo, monospace;
		font-weight: 600;
		font-size: 12px;
	}
	.val {
		font-family: ui-monospace, Menlo, monospace;
		font-size: 12px;
		color: #334155;
	}
	.muted {
		color: #64748b;
	}
</style>
