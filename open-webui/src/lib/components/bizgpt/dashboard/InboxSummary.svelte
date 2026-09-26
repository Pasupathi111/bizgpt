<script lang="ts">
	import type { DashboardData } from '$lib/apis/bizgpt';
	import Icon from './Icon.svelte';
	import Panel from './Panel.svelte';
	import { timeAgo } from './tones';

	export let inbox: DashboardData['inbox'] = null;
	export let reason: string | null = null;
	export let openHref: string;

	const R = 40;
	const C = 2 * Math.PI * R;
	const GAP = 1.5; // arc gap between segments

	$: recent = inbox?.recent ?? [];
	$: b = inbox?.breakdown;
	$: total = b?.total ?? recent.length;
	$: segments = [
		{ label: 'Unread', value: b?.unread ?? inbox?.unread ?? 0, color: '#3b82f6' },
		{ label: 'Important', value: b?.important ?? 0, color: '#f97316' },
		{ label: 'Starred', value: b?.starred ?? 0, color: '#10b981' },
		{ label: 'Others', value: b?.others ?? 0, color: '#9ca3af' }
	];
	// stroke-dasharray arcs, laid end to end around the ring
	$: arcs = (() => {
		const sum = segments.reduce((a, s) => a + s.value, 0);
		let offset = 0;
		return segments
			.filter((s) => s.value > 0)
			.map((s) => {
				const len = sum ? (s.value / sum) * C : 0;
				const arc = { color: s.color, dash: `${Math.max(len - GAP, 0.5)} ${C}`, offset: -offset };
				offset += len;
				return arc;
			});
	})();
</script>

<Panel title="Inbox Summary" icon="mail" tone="rose" actionLabel={inbox ? 'Open inbox' : ''} actionHref={openHref}>
	{#if !inbox}
		<div class="flex flex-1 flex-col items-center justify-center gap-2 py-8 text-center">
			<div class="flex size-10 items-center justify-center rounded-full bg-gray-100 text-gray-500 dark:bg-gray-800">
				<Icon name="lock" className="size-5" />
			</div>
			<div class="text-sm text-gray-600 dark:text-gray-300">
				{reason === 'restricted' ? 'The shared mailbox is available to admins only.' : 'The mailbox is not reachable right now.'}
			</div>
		</div>
	{:else}
		<div class="flex items-center gap-5">
			<div class="relative size-32 shrink-0">
				<svg viewBox="0 0 100 100" class="size-32 -rotate-90">
					<circle cx="50" cy="50" r={R} fill="none" stroke-width="12" class="stroke-gray-100 dark:stroke-gray-800" />
					{#each arcs as a}
						<circle cx="50" cy="50" r={R} fill="none" stroke-width="12" stroke={a.color} stroke-dasharray={a.dash} stroke-dashoffset={a.offset} />
					{/each}
				</svg>
				<div class="absolute inset-0 flex flex-col items-center justify-center">
					<div class="text-2xl font-semibold tabular-nums text-gray-900 dark:text-white">
						{total}{b?.capped ? '+' : ''}
					</div>
					<div class="text-[11px] text-gray-500">Total</div>
				</div>
			</div>
			<ul class="flex min-w-0 flex-1 flex-col gap-2.5">
				{#each segments as s}
					<li class="flex items-center justify-between gap-2 text-[0.8125rem]">
						<span class="flex items-center gap-2 text-gray-700 dark:text-gray-200">
							<span class="size-2.5 rounded-full" style="background:{s.color}"></span>{s.label}
						</span>
						<span class="tabular-nums font-medium text-gray-900 dark:text-gray-100">{s.value}</span>
					</li>
				{/each}
				<li class="truncate pt-1 text-[11px] text-gray-400">{inbox.mailbox}</li>
			</ul>
		</div>

		<div class="mt-4 text-xs font-medium text-gray-500 dark:text-gray-400">Recent messages</div>
		<ul class="mt-1 flex flex-col">
			{#each recent.slice(0, 4) as m (m.id)}
				<li>
					<a href={m.link || openHref} target={m.link ? '_blank' : undefined} rel="noopener noreferrer"
						class="flex items-center gap-3 rounded-xl px-1.5 py-2 hover:bg-gray-50 dark:hover:bg-gray-850">
						<div class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300">
							<Icon name="mail" className="size-4" />
						</div>
						<div class="min-w-0 flex-1">
							<div class="truncate text-[0.8125rem] {m.unread ? 'font-semibold text-gray-900 dark:text-white' : 'font-medium text-gray-800 dark:text-gray-100'}">
								{m.from}
							</div>
							<div class="truncate text-xs text-gray-500 dark:text-gray-400">{m.subject}</div>
						</div>
						<div class="flex shrink-0 flex-col items-end gap-1">
							<span class="text-[11px] text-gray-400">{timeAgo(m.at)}</span>
							{#if m.unread}<span class="size-2 rounded-full bg-sky-500"></span>{/if}
						</div>
					</a>
				</li>
			{:else}
				<li class="py-4 text-center text-sm text-gray-500">Inbox is empty.</li>
			{/each}
		</ul>
	{/if}
</Panel>
