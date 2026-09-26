<script lang="ts">
	import Icon from './Icon.svelte';
	import { TONES, type Tone } from './tones';

	export let title: string;
	export let value: string | number;
	export let caption: string;
	export let icon: string;
	export let tone: Tone = 'violet';
	export let href: string | null = null;
	export let external = false;
	export let muted = false;
</script>

<svelte:element
	this={href ? 'a' : 'div'}
	href={href ?? undefined}
	target={href && external ? '_blank' : undefined}
	rel={href && external ? 'noopener noreferrer' : undefined}
	class="group flex flex-col gap-3 rounded-2xl border border-gray-100 bg-white p-4 transition dark:border-gray-850 dark:bg-gray-900 {href
		? 'hover:border-gray-200 hover:shadow-sm dark:hover:border-gray-800'
		: ''}"
>
	<div class="flex items-center gap-3">
		<div class="flex size-9 sm:size-10 shrink-0 items-center justify-center rounded-xl {TONES[tone].tile}">
			<Icon name={icon} />
		</div>
		<div class="min-w-0 truncate text-sm font-medium text-gray-800 dark:text-gray-100 leading-tight">{title}</div>
	</div>
	<div class="flex items-end justify-between gap-2">
		<div>
			<div
				class="text-2xl font-semibold tabular-nums {muted
					? 'text-gray-400 dark:text-gray-500'
					: 'text-gray-900 dark:text-white'}"
			>
				{value}
			</div>
			<div class="text-xs text-gray-500 dark:text-gray-400">{caption}</div>
		</div>
		{#if href}
			<div
				class="flex size-7 items-center justify-center rounded-full border border-gray-200 text-gray-500 transition group-hover:translate-x-0.5 group-hover:text-gray-800 dark:border-gray-700 dark:text-gray-400 dark:group-hover:text-gray-100"
			>
				<Icon name="arrow" className="size-3.5" strokeWidth="2" />
			</div>
		{/if}
	</div>
</svelte:element>
