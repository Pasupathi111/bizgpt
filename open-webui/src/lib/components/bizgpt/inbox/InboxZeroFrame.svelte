<script lang="ts">
	// Embeds the self-hosted Inbox Zero ("Biz Inbox", served same-origin at /inbox_zero by nginx).
	// Framing is allowed for this origin only (frame-ancestors 'self'); see deploy/inbox-zero.
	// The Biz GPT token is exchanged for an Inbox Zero session on the shared mailbox, so the
	// frame opens straight on the inbox with no Google sign-in or account picker.
	import { onMount } from 'svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import InboxIcon from '../icons/Inbox.svelte';

	const SSO_URL = '/inbox_zero/api/bizgpt/sso';

	let src = '';
	let mailbox = '';
	let frame: HTMLIFrameElement;
	let loading = true;
	let error = '';

	const connect = async () => {
		error = '';
		loading = true;
		try {
			const res = await fetch(SSO_URL, {
				method: 'POST',
				credentials: 'include',
				headers: { Authorization: `Bearer ${localStorage.token ?? ''}` }
			});
			const data = await res.json().catch(() => null);
			if (!res.ok || !data?.emailAccountId) {
				error = data?.error ?? 'Biz Inbox is not reachable right now.';
				return;
			}
			mailbox = data.email;
			src = `/inbox_zero/${data.emailAccountId}/mail?type=inbox`;
		} catch {
			error = 'Biz Inbox is not reachable right now.';
		}
	};

	onMount(connect);

	const reload = () => {
		if (!src) return connect();
		loading = true;
		frame?.contentWindow?.location.reload();
	};
</script>

<div class="flex h-full flex-col">
	<header
		class="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-2.5 dark:border-gray-850"
	>
		<div class="flex items-center gap-2.5">
			<div
				class="flex size-8 items-center justify-center rounded-lg bg-rose-100 text-rose-600 dark:bg-rose-500/15 dark:text-rose-300"
			>
				<InboxIcon className="size-4" />
			</div>
			<div>
				<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Biz Inbox</h1>
				{#if mailbox}<p class="text-xs text-gray-500 dark:text-gray-400">{mailbox}</p>{/if}
			</div>
		</div>
		<div class="flex items-center gap-2">
			<button
				type="button"
				on:click={reload}
				class="rounded-lg border border-gray-200 px-2.5 py-1 text-xs text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-850"
			>
				Reload
			</button>
			{#if src}
			<a
				href={src}
				target="_blank"
				rel="noopener noreferrer"
				class="rounded-lg border border-gray-200 px-2.5 py-1 text-xs text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-850"
			>
				Open in new tab
			</a>
			{/if}
		</div>
	</header>

	{#if error}
		<div class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
			<p class="text-sm text-gray-600 dark:text-gray-300">{error}</p>
			<button type="button" on:click={connect} class="text-xs text-gray-500 underline">Try again</button>
		</div>
	{:else}
		<div class="relative flex-1">
			{#if loading}
				<div class="absolute inset-0 flex items-center justify-center"><Spinner className="size-5" /></div>
			{/if}
			{#if src}
				<iframe
					bind:this={frame}
					{src}
					title="Biz Inbox"
					class="absolute inset-0 h-full w-full border-0"
					on:load={() => (loading = false)}
				></iframe>
			{/if}
		</div>
	{/if}
</div>
