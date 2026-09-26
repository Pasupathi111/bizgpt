<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { WEBUI_NAME, showSidebar, mobile, user } from '$lib/stores';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import WhatsAppCard from '$lib/components/bizgpt/integrations/WhatsAppCard.svelte';

	const i18n = getContext('i18n');

	onMount(() => {
		if ($user?.role !== 'admin') goto('/');
	});
</script>

<svelte:head>
	<title>{$i18n.t('Integrations')} / {$WEBUI_NAME}</title>
</svelte:head>

<div
	class="flex h-screen max-h-[100dvh] w-full max-w-full flex-col transition-width duration-200 ease-in-out {$showSidebar
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	{#if $mobile}
		<nav class="drag-region w-full px-2.5 pt-1.5">
			<Tooltip content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')} interactive={true}>
				<button
					id="sidebar-toggle-button"
					class="flex cursor-pointer rounded-lg transition hover:bg-gray-100 dark:hover:bg-gray-850"
					on:click={() => showSidebar.set(!$showSidebar)}
					aria-label={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
				>
					<div class="self-center p-1.5"><SidebarIcon className="size-4" /></div>
				</button>
			</Tooltip>
		</nav>
	{/if}
	<div class="flex-1 overflow-y-auto bg-gray-50/60 dark:bg-gray-950">
		<div class="mx-auto w-full max-w-5xl px-4 py-6 md:px-8">
			<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('Integrations')}</h1>
			<p class="mb-5 text-sm text-gray-500 dark:text-gray-400">
				Channels and services connected to Biz GPT.
			</p>
			{#if $user?.role === 'admin'}
				<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
					<WhatsAppCard />
				</div>
			{/if}
		</div>
	</div>
</div>
