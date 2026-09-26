<script lang="ts">
	import type { DashboardData } from '$lib/apis/bizgpt';
	import Icon from './Icon.svelte';
	import Panel from './Panel.svelte';
	import { timeAgo } from './tones';

	export let inbox: DashboardData['inbox'] = null;
	export let reason: string | null = null;
	export let openHref: string;

	const R = 42;
	const C = 2 * Math.PI * R;

	$: recent = inbox?.recent ?? [];
	$: unread = inbox?.unread ?? 0;
	$: unreadRecent = recent.filter((m) => m.unread).length;
	$: readRecent = recent.length - unreadRecent;
	// Ring: share of unread among the latest messages (full ring when all unread).
	$: unreadShare = recent.length ? unreadRecent / recent.length : 0;
	$: sources = [
		{ label: 'Unread', value: unread, color: '#f43f5e' },
		{ label: 'Read (latest)', value: readRecent, color: '#10b981' }
	];
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
			<div class="relative size-28 shrink-0">
				<svg viewBox="0 0 100 100" class="size-28 -rotate-90">
					<circle cx="50" cy="50" r={R} fill="none" stroke-width="10" class="stroke-emerald-500/80" />
					{#if unreadShare > 0}
						<circle cx="50" cy="50" r={R} fill="none" stroke-width="10" stroke="#f43f5e"
							stroke-dasharray="{C * unreadShare} {C}" stroke-linecap={unreadShare < 1 ? 'round' : 'butt'} />
					{/if}
				</svg>
				<div class="absolute inset-0 flex flex-col items-center justify-center">
					<div class="text-2xl font-semibold tabular-nums text-gray-900 dark:text-white">
						{unread}{inbox.unread_capped ? '+' : ''}
					</div>
					<div class="text-[11px] text-gray-500">Unread</div>
				</div>
			</div>
			<ul class="flex min-w-0 flex-1 flex-col gap-2">
				<li class="truncate text-xs text-gray-500 dark:text-gray-400">{inbox.mailbox}</li>
				{#each sources as s}
					<li class="flex items-center justify-between gap-2 text-[0.8125rem]">
						<span class="flex items-center gap-2 text-gray-700 dark:text-gray-200">
							<span class="size-2.5 rounded-full" style="background:{s.color}"></span>{s.label}
						</span>
						<span class="tabular-nums font-medium text-gray-900 dark:text-gray-100">{s.value}</span>
					</li>
				{/each}
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
