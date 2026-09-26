<script lang="ts">
	import type { DashboardIntegration } from '$lib/apis/bizgpt';
	import Icon from './Icon.svelte';
	import Panel from './Panel.svelte';
	import { STATUS_BADGE, STATUS_LABEL, TONES } from './tones';

	export let items: DashboardIntegration[] = [];
	export let manageHref: string | null = null;

	const KIND = {
		gmail: ['mail', 'rose'],
		outlook: ['mail', 'sky'],
		dify: ['workflow', 'violet'],
		forms: ['form', 'emerald'],
		nango: ['cloud', 'sky']
	} as const;

	const DOT: Record<string, string> = {
		connected: 'bg-emerald-500',
		restricted: 'bg-amber-400',
		not_connected: 'bg-amber-400',
		not_configured: 'bg-amber-400'
	};
</script>

<Panel title="Integrations Status" icon="link" tone="orange" actionLabel={manageHref ? 'Manage' : ''} actionHref={manageHref}>
	<ul class="flex flex-col gap-1">
		{#each items as item (item.id)}
			{@const [icon, tone] = KIND[item.kind] ?? ['link', 'orange']}
			<li class="flex items-center gap-3 rounded-xl px-1.5 py-2">
				<div class="flex size-8 shrink-0 items-center justify-center rounded-lg {TONES[tone].tile}">
					<Icon name={icon} className="size-4" />
				</div>
				<div class="min-w-0 flex-1">
					<div class="truncate text-[0.8125rem] font-medium text-gray-800 dark:text-gray-100">{item.name}</div>
					<div class="truncate text-xs text-gray-500 dark:text-gray-400">{item.detail ?? ''}</div>
				</div>
				<span
					class="flex shrink-0 items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium {STATUS_BADGE[
						item.status
					] ?? STATUS_BADGE.info}"
				>
					<span class="size-1.5 rounded-full {DOT[item.status] ?? 'bg-rose-500'}"></span>
					{STATUS_LABEL[item.status] ?? item.status}
				</span>
			</li>
		{/each}
	</ul>
</Panel>
