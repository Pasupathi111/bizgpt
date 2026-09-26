<!-- "Meet your AI Assistant" promo card with a small robot illustration. -->
<script lang="ts">
	import Robot from '../common/Robot.svelte';
</script>

<div
	class="relative flex items-center gap-4 overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-50 to-violet-50 p-5 dark:from-indigo-500/10 dark:to-violet-500/10"
>
	<div class="relative z-10 min-w-0 flex-1">
		<div
			class="flex size-9 items-center justify-center rounded-full bg-white text-orange-500 shadow-sm dark:bg-gray-900"
		>
			<svg viewBox="0 0 24 24" fill="currentColor" class="size-5" aria-hidden="true">
				<path d="M12 2l1.8 5.4L19 9l-5.2 1.6L12 16l-1.8-5.4L5 9l5.2-1.6L12 2Z" />
			</svg>
		</div>
		<div class="mt-3 text-base font-semibold text-gray-900 dark:text-white">Meet your AI Assistant</div>
		<p class="mt-1 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
			Get answers, automate work, and manage your tools — all in one place.
		</p>
	</div>

	<Robot className="relative z-10 h-28 w-24 shrink-0" />
</div>
