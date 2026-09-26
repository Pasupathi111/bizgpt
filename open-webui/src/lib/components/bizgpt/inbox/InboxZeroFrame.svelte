<script lang="ts">
	// Embeds the self-hosted Inbox Zero (served same-origin at /inbox_zero by nginx).
	// Framing is allowed for this origin only (frame-ancestors 'self'); see deploy/inbox-zero.
	import { onMount } from 'svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import InboxIcon from '../icons/Inbox.svelte';

	// Mailbox view of the connected Biz GPT mailbox (dbizgpt.assistant@gmail.com).
	const INBOX_ZERO_MAIL_URL =
		'/inbox_zero/cmui5aalq000101rvf1a31gkk/mail?tab=all&thread-id=1a05d6fe0a602b6c';

	export let src = INBOX_ZERO_MAIL_URL;

	let frame: HTMLIFrameElement;
	let loading = true;
	let reachable = true;
	let signedIn = true;

	onMount(async () => {
		// The login page and Google sign-in cannot run inside a frame; detect a missing
		// session up front and offer a full-tab sign-in instead of a blank frame.
		try {
			const res = await fetch('/inbox_zero/api/auth/get-session', { credentials: 'include' });
			reachable = res.ok;
			const session = res.ok ? await res.json() : null;
			if (!session) signedIn = false;
		} catch {
			reachable = false;
		}
	});

	const reload = () => {
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
				<h1 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Inbox</h1>
				<p class="text-xs text-gray-500 dark:text-gray-400">Inbox Zero · dbizgpt.assistant@gmail.com</p>
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
			<a
				href={src}
				target="_blank"
				rel="noopener noreferrer"
				class="rounded-lg border border-gray-200 px-2.5 py-1 text-xs text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-850"
			>
				Open in new tab
			</a>
		</div>
	</header>

	{#if !reachable}
		<div class="flex flex-1 items-center justify-center p-6 text-sm text-gray-500">
			Inbox Zero is not reachable right now.
		</div>
	{:else if !signedIn}
		<div class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
			<p class="text-sm text-gray-600 dark:text-gray-300">
				Sign in to Inbox Zero once in a full tab (Google sign-in cannot run inside an embedded page),
				then come back here.
			</p>
			<a
				href="/inbox_zero/login"
				target="_blank"
				rel="noopener noreferrer"
				class="rounded-lg bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 dark:bg-white dark:text-gray-900"
			>
				Sign in to Inbox Zero
			</a>
			<button type="button" on:click={() => location.reload()} class="text-xs text-gray-500 underline">
				I've signed in, reload
			</button>
		</div>
	{:else}
		<div class="relative flex-1">
			{#if loading}
				<div class="absolute inset-0 flex items-center justify-center"><Spinner className="size-5" /></div>
			{/if}
			<iframe
				bind:this={frame}
				{src}
				title="Inbox Zero"
				class="absolute inset-0 h-full w-full border-0"
				on:load={() => (loading = false)}
			></iframe>
		</div>
	{/if}
</div>
