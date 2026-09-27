<script lang="ts">
	import { getContext } from 'svelte';
	import { WEBUI_NAME, showSidebar, mobile } from '$lib/stores';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';
	import InboxZeroFrame from '$lib/components/bizgpt/inbox/InboxZeroFrame.svelte';
	import OrdersPanel from '$lib/components/bizgpt/inbox/OrdersPanel.svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	const i18n = getContext('i18n');

	const TABS = [
		{ id: 'mail', label: 'Mail' },
		{ id: 'orders', label: 'Action' }
	];
	$: tab = $page.url.searchParams.get('tab') === 'orders' ? 'orders' : 'mail';
	const selectTab = (id: string) => {
		const url = new URL($page.url);
		if (id === 'mail') url.searchParams.delete('tab');
		else url.searchParams.set('tab', id);
		goto(url, { replaceState: true, keepFocus: true, noScroll: true });
	};
</script>

<svelte:head>
	<title>{$i18n.t('Biz Inbox')} / {$WEBUI_NAME}</title>
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
	<div class="flex gap-1 border-b border-gray-100 px-4 pt-2 dark:border-gray-850" role="tablist">
		{#each TABS as t}
			<button
				type="button"
				role="tab"
				aria-selected={tab === t.id}
				on:click={() => selectTab(t.id)}
				class="-mb-px border-b-2 px-3 pb-2 text-sm font-medium transition {tab === t.id
					? 'border-gray-900 text-gray-900 dark:border-white dark:text-white'
					: 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}">{t.label}</button
			>
		{/each}
	</div>
	<div class="flex-1 min-h-0">
		{#if tab === 'orders'}
			<OrdersPanel />
		{:else}
			<InboxZeroFrame />
		{/if}
	</div>
</div>
