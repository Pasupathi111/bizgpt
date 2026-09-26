<script lang="ts">
	// Sidebar footer shortcut: start a chat with the Biz GPT Assistant model.
	import { withBasePath } from '$lib/constants';
	export let onClick: () => void = () => {};
</script>

<a
	href={withBasePath('/?models=bizgpt-assistant')}
	draggable="false"
	on:click={onClick}
	class="group mx-1 mb-1.5 flex items-center gap-3 rounded-2xl bg-gradient-to-r from-orange-50 to-violet-50 px-3 py-2.5 transition hover:from-orange-100 hover:to-violet-100 dark:from-orange-500/10 dark:to-violet-500/10"
>
	<svg viewBox="0 0 24 24" fill="currentColor" class="size-5 shrink-0 text-orange-500" aria-hidden="true">
		<path d="M12 2l1.8 5.4L19 9l-5.2 1.6L12 16l-1.8-5.4L5 9l5.2-1.6L12 2Zm6 12 .9 2.1L21 17l-2.1.9L18 20l-.9-2.1L15 17l2.1-.9L18 14Z" />
	</svg>
	<div class="min-w-0 flex-1">
		<div class="text-[0.875rem] font-semibold text-gray-900 dark:text-white">AI Assistant</div>
		<div class="truncate text-xs text-gray-500 dark:text-gray-400">Ask Biz GPT anything…</div>
	</div>
	<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 text-gray-400 transition group-hover:translate-x-0.5" aria-hidden="true">
		<path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 0 1 .02-1.06L11.168 10 7.23 6.29a.75.75 0 1 1 1.04-1.08l4.5 4.25a.75.75 0 0 1 0 1.08l-4.5 4.25a.75.75 0 0 1-1.06-.02Z" clip-rule="evenodd" />
	</svg>
</a>
