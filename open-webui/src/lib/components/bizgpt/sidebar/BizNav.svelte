<script lang="ts">
	// Biz GPT primary navigation for the expanded sidebar (New Chat, Dashboard, Workspace, Productivity).
	import { page } from '$app/stores';
	import { showSearch } from '$lib/stores';
	import { withBasePath } from '$lib/constants';
	import Icon from '../dashboard/Icon.svelte';
	import InboxIcon from '../icons/Inbox.svelte';

	export let newChatHandler: (e?: Event) => void = () => {};
	export let itemClickHandler: () => void = () => {};
	export let isAdmin = false;
	export let showNotes = true;
	export let showWorkspace = true;

	const chat = (model: string, q = '') =>
		withBasePath(`/?models=${encodeURIComponent(model)}${q ? `&q=${encodeURIComponent(q)}` : ''}`);

	type Item = { id: string; label: string; href?: string; icon: string; tone: string; match?: string; onClick?: () => void };

	$: workspace = [
		{ id: 'dify', label: 'Dify Workflows', href: withBasePath('/lead-generation'), icon: 'workflow', tone: 'text-violet-500', match: '/lead-generation' },
		{ id: 'forms', label: 'Dynamic Forms', href: chat(isAdmin ? 'bizgpt-form-builder' : 'bizgpt-assistant'), icon: 'form', tone: 'text-emerald-500' },
		...(isAdmin
			? [{ id: 'integrations', label: 'Integrations', href: withBasePath('/admin/settings/tools'), icon: 'link', tone: 'text-orange-500', match: '/admin/settings/tools' }]
			: []),
		{ id: 'inbox', label: 'Inbox Zero', href: withBasePath('/inbox'), icon: 'inbox', tone: 'text-rose-500', match: '/inbox' },
		{ id: 'nango', label: 'Nango', href: chat('bizgpt-assistant', 'Show my integration status'), icon: 'cloud', tone: 'text-sky-500' }
	] as Item[];

	$: productivity = [
		{ id: 'chats', label: 'Chats', href: withBasePath('/'), icon: 'chat', tone: '', match: '/c/', onClick: newChatHandler },
		...(showNotes ? [{ id: 'notes', label: 'Notes', href: withBasePath('/notes'), icon: 'note', tone: '', match: '/notes' }] : []),
		...(showWorkspace ? [{ id: 'workspace', label: 'Workspace', href: withBasePath('/workspace'), icon: 'grid', tone: '', match: '/workspace' }] : []),
		{ id: 'search', label: 'Search', icon: 'search', tone: '', onClick: () => showSearch.set(true) }
	] as Item[];

	$: path = $page.url.pathname;
	const active = (item: Item) => !!item.match && (path === item.match || path.startsWith(item.match));

	// Extra outline icons not in the dashboard set.
	const extra: Record<string, string> = {
		chat: 'M2.25 12.76c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 0 1 1.037-.443 48.282 48.282 0 0 0 5.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z',
		note: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
		grid: 'M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z',
		search: 'm21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
		home: 'm2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25'
	};
</script>

{#snippet itemIcon(item)}
	{#if item.icon === 'inbox'}
		<InboxIcon className="size-[1.15rem] {item.tone}" strokeWidth="1.6" />
	{:else if extra[item.icon]}
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="size-[1.15rem] {item.tone}" aria-hidden="true">
			<path stroke-linecap="round" stroke-linejoin="round" d={extra[item.icon]} />
		</svg>
	{:else}
		<Icon name={item.icon} className="size-[1.15rem] {item.tone}" strokeWidth="1.6" />
	{/if}
{/snippet}

{#snippet navItem(item)}
	{@const on = active(item)}
	{#if item.href}
		<a
			id="sidebar-{item.id}-button"
			href={item.href}
			draggable="false"
			class="flex items-center gap-3 rounded-xl px-3 py-2 text-[0.875rem] transition {on
				? 'bg-blue-50 font-semibold text-[#0f1a3d] dark:bg-white/[0.06] dark:text-white'
				: 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-900'}"
			on:click={(e) => {
				item.onClick?.(e);
				itemClickHandler();
			}}
		>
			{@render itemIcon(item)}
			<span class="truncate">{item.label}</span>
		</a>
	{:else}
		<button
			id="sidebar-{item.id}-button"
			type="button"
			class="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-[0.875rem] text-gray-700 transition hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-900"
			on:click={() => item.onClick?.()}
		>
			{@render itemIcon(item)}
			<span class="truncate">{item.label}</span>
		</button>
	{/if}
{/snippet}

<nav class="flex flex-col gap-0.5 px-2" aria-label="Biz GPT">
	<a
		id="sidebar-new-chat-button"
		href={withBasePath('/')}
		draggable="false"
		class="mb-2 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-orange-500 to-amber-500 px-3 py-2.5 text-[0.875rem] font-semibold text-white shadow-sm shadow-orange-500/30 transition hover:from-orange-600 hover:to-amber-500"
		on:click={newChatHandler}
	>
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="size-[1.15rem]" aria-hidden="true">
			<path stroke-linecap="round" stroke-linejoin="round" d={extra.chat} />
		</svg>
		New Chat
	</a>

	{@render navItem({ id: 'dashboard', label: 'Dashboard', href: withBasePath('/dashboard'), icon: 'home', tone: 'text-blue-600 dark:text-blue-400', match: '/dashboard' })}

	<div class="mt-4 px-3 pb-1 text-[0.7rem] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Workspace</div>
	{#each workspace as item (item.id)}
		{@render navItem(item)}
	{/each}

	<div class="mx-3 my-3 h-px bg-gray-200/70 dark:bg-gray-800"></div>
	<div class="px-3 pb-1 text-[0.7rem] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Productivity</div>
	{#each productivity as item (item.id)}
		{@render navItem(item)}
	{/each}
</nav>
