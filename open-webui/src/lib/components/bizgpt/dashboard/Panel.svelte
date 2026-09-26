<script lang="ts">
	import Icon from './Icon.svelte';
	import { TONES, type Tone } from './tones';

	export let title: string;
	export let subtitle = '';
	export let icon: string;
	export let tone: Tone = 'violet';
	export let actionLabel = '';
	export let actionHref: string | null = null;
	export let className = '';
</script>

<section
	class="flex min-w-0 flex-col rounded-2xl border border-gray-100 bg-white p-4 dark:border-gray-850 dark:bg-gray-900 {className}"
>
	<header class="mb-3 flex items-start justify-between gap-3">
		<div class="flex items-center gap-2.5">
			<div class="flex size-8 shrink-0 items-center justify-center rounded-lg {TONES[tone].tile}">
				<Icon name={icon} className="size-4" />
			</div>
			<div>
				<h2 class="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
				{#if subtitle}
					<p class="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
				{/if}
			</div>
		</div>
		<slot name="action">
			{#if actionLabel && actionHref}
				<a href={actionHref} class="shrink-0 text-xs font-medium {TONES[tone].text} hover:underline">
					{actionLabel}
				</a>
			{/if}
		</slot>
	</header>
	<slot />
</section>
