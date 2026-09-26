<script lang="ts">
	import type { DashboardActivity } from '$lib/apis/bizgpt';
	import Icon from './Icon.svelte';
	import Panel from './Panel.svelte';
	import { STATUS_BADGE, STATUS_LABEL, TONES, timeAgo } from './tones';

	export let items: DashboardActivity[] = [];

	const ICON = { form: ['form', 'emerald'], workflow: ['play', 'violet'], email: ['mail', 'rose'] } as const;
</script>

<Panel title="Recent Activity" icon="clock" tone="sky">
	{#if items.length === 0}
		<div class="flex flex-1 flex-col items-center justify-center py-8 text-center text-sm text-gray-500">
			No activity yet. Open a form or run a workflow from chat.
		</div>
	{:else}
		<ul class="flex flex-col gap-1">
			{#each items as item}
				{@const [icon, tone] = ICON[item.type] ?? ['bolt', 'sky']}
				<li class="flex items-center gap-3 rounded-xl px-1.5 py-2">
					<div class="flex size-8 shrink-0 items-center justify-center rounded-lg {TONES[tone].tile}">
						<Icon name={icon} className="size-4" />
					</div>
					<div class="min-w-0 flex-1">
						<div class="truncate text-[0.8125rem] font-medium text-gray-800 dark:text-gray-100">
							{item.title}
						</div>
						<div class="truncate text-xs text-gray-500 dark:text-gray-400">
							{timeAgo(item.at)}{item.detail ? ` · ${item.detail}` : ''}
						</div>
					</div>
					<span
						class="shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium {STATUS_BADGE[item.status] ??
							STATUS_BADGE.info}"
					>
						{STATUS_LABEL[item.status] ?? item.status}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</Panel>
