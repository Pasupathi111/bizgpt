<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';

	const dispatch = createEventDispatcher<{ toast: { message: string; kind?: 'success' | 'error' | 'info' } }>();

	let settings = {
		model: 'claude-sonnet-5',
		threshold: 70,
		retries: 3,
		timeout: 60,
		timezone: 'Asia/Kolkata (IST)',
		crm: 'HubSpot',
		notifyFailures: true,
		notifyHotLeads: true,
		dedupe: true,
		piiMasking: true,
		difyUrl: 'https://dify.bizgpt.ai'
	};

	const toggles: { key: 'notifyFailures' | 'notifyHotLeads' | 'dedupe' | 'piiMasking'; label: string; hint: string }[] = [
		{ key: 'notifyFailures', label: 'Alert on failed runs', hint: 'Email + WhatsApp the workflow owner' },
		{ key: 'notifyHotLeads', label: 'Hot-lead notifications', hint: 'Ping sales when a lead scores above the threshold' },
		{ key: 'dedupe', label: 'Deduplicate leads', hint: 'Match on email + company domain before creating CRM records' },
		{ key: 'piiMasking', label: 'Mask PII in logs', hint: 'Emails and phone numbers are redacted in execution logs' }
	];
</script>

<div class="wrap">
	<section class="lg-card">
		<h3><LGIcon name="cpu" size={16} /> Defaults</h3>
		<div class="grid">
			<label><span class="lg-label">Default LLM</span>
				<select class="lg-select" bind:value={settings.model}><option>claude-sonnet-5</option><option>claude-opus-5-5</option><option>claude-haiku-4-5</option></select>
			</label>
			<label><span class="lg-label">Qualified-lead threshold</span>
				<input class="lg-input" type="number" min="0" max="100" bind:value={settings.threshold} />
			</label>
			<label><span class="lg-label">Primary CRM</span>
				<select class="lg-select" bind:value={settings.crm}><option>HubSpot</option><option>Salesforce</option><option>Zoho CRM</option><option>Pipedrive</option></select>
			</label>
			<label><span class="lg-label">Timezone</span>
				<select class="lg-select" bind:value={settings.timezone}><option>Asia/Kolkata (IST)</option><option>UTC</option><option>America/New_York</option><option>Europe/London</option></select>
			</label>
		</div>
	</section>

	<section class="lg-card">
		<h3><LGIcon name="refresh" size={16} /> Execution</h3>
		<div class="grid">
			<label><span class="lg-label">Retries on failure</span><input class="lg-input" type="number" min="0" max="10" bind:value={settings.retries} /></label>
			<label><span class="lg-label">Node timeout (seconds)</span><input class="lg-input" type="number" min="5" bind:value={settings.timeout} /></label>
			<label style="grid-column:1/-1"><span class="lg-label">Dify workspace URL</span><input class="lg-input" bind:value={settings.difyUrl} /></label>
		</div>
	</section>

	<section class="lg-card">
		<h3><LGIcon name="bell" size={16} /> Notifications & data</h3>
		{#each toggles as t}
			<div class="row">
				<div><div style="font-weight:600">{t.label}</div><div class="lg-hint">{t.hint}</div></div>
				<button class="lg-switch" class:on={settings[t.key]} on:click={() => (settings[t.key] = !settings[t.key])} aria-label={t.label}></button>
			</div>
		{/each}
	</section>

	<div style="display:flex;justify-content:flex-end;gap:8px">
		<button class="lg-btn">Cancel</button>
		<button class="lg-btn primary" on:click={() => dispatch('toast', { message: 'Settings saved', kind: 'success' })}><LGIcon name="check" size={14} /> Save settings</button>
	</div>
</div>

<style>
	.wrap {
		max-width: 820px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	section {
		padding: 16px 18px;
	}
	h3 {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
		margin: 0 0 12px;
	}
	.grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px 16px;
	}
	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 14px;
		padding: 10px 0;
		border-top: 1px solid #eef1f5;
	}
	.row:first-of-type {
		border-top: 0;
	}
	@media (max-width: 640px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>
