<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { models } from '$lib/stores';
	import { withBasePath } from '$lib/constants';
	import {
		getWhatsApp,
		getWhatsAppConversations,
		testWhatsApp,
		updateWhatsAppSettings,
		type WhatsAppConversation,
		type WhatsAppOverview
	} from '$lib/apis/bizgpt';

	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Icon from '../dashboard/Icon.svelte';
	import { STATUS_BADGE, STATUS_LABEL, TONES, timeAgo } from '../dashboard/tones';

	let data: WhatsAppOverview | null = null;
	let conversations: WhatsAppConversation[] = [];
	let loading = true;
	let testing = false;
	let saving = false;
	let manage = false;
	let confirmDisconnect = false;
	let testResult: Awaited<ReturnType<typeof testWhatsApp>> | null = null;

	const errorText = (e: unknown) => (typeof e === 'string' ? e : 'Something went wrong');

	async function load() {
		try {
			data = await getWhatsApp(localStorage.token);
		} catch (e) {
			data = { reachable: false, detail: errorText(e) };
		} finally {
			loading = false;
		}
	}

	async function loadConversations() {
		try {
			conversations = await getWhatsAppConversations(localStorage.token, 8);
		} catch {
			conversations = [];
		}
	}

	async function save(patch: Parameters<typeof updateWhatsAppSettings>[1], message: string) {
		saving = true;
		try {
			const account = await updateWhatsAppSettings(localStorage.token, patch);
			data = { ...(data as WhatsAppOverview), account };
			toast.success(message);
		} catch (e) {
			toast.error(errorText(e));
		} finally {
			saving = false;
		}
	}

	async function runTest() {
		testing = true;
		testResult = null;
		try {
			testResult = await testWhatsApp(localStorage.token);
			testResult.ok ? toast.success('WhatsApp and Biz GPT are both reachable') : toast.error('Connection test found a problem');
			await load();
		} catch (e) {
			toast.error(errorText(e));
		} finally {
			testing = false;
		}
	}

	function toggleManage() {
		manage = !manage;
		if (manage) loadConversations();
	}

	onMount(load);

	$: account = data?.account;
	$: status = data?.status;
	$: connection = !data?.reachable
		? 'down'
		: !account?.is_active
			? 'not_connected'
			: status?.whatsapp_api?.status === 'not_configured'
				? 'not_configured'
				: status && !status.whatsapp_api?.ok
					? 'down'
					: 'connected';
	$: agentName = $models.find((m) => m.id === account?.agent_model)?.name ?? account?.agent_model ?? '';

	const DOT: Record<string, string> = {
		connected: 'bg-emerald-500',
		not_connected: 'bg-amber-400',
		not_configured: 'bg-amber-400'
	};

	const check = (ok: boolean | undefined) =>
		ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400';

	const button =
		'rounded-lg px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50';
</script>

<ConfirmDialog
	bind:show={confirmDisconnect}
	title="Disconnect WhatsApp?"
	message="Biz GPT will stop answering WhatsApp customers. Incoming messages are still saved, and you can reconnect at any time."
	confirmLabel="Disconnect"
	on:confirm={() => save({ is_active: false }, 'WhatsApp disconnected')}
/>

<section class="flex min-w-0 flex-col rounded-2xl border border-gray-100 bg-white p-4 dark:border-gray-850 dark:bg-gray-900">
	<header class="mb-4 flex items-start justify-between gap-3">
		<div class="flex items-center gap-2.5">
			<div class="flex size-9 shrink-0 items-center justify-center rounded-lg {TONES.emerald.tile}">
				<Icon name="chat" className="size-5" />
			</div>
			<div>
				<h2 class="text-sm font-semibold text-gray-900 dark:text-gray-100">WhatsApp</h2>
				<p class="text-xs text-gray-500 dark:text-gray-400">Business WhatsApp · Meta Cloud API</p>
			</div>
		</div>
		{#if !loading}
			<span
				class="flex shrink-0 items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium {STATUS_BADGE[connection] ??
					STATUS_BADGE.info}"
			>
				<span class="size-1.5 rounded-full {DOT[connection] ?? 'bg-rose-500'}"></span>
				{connection === 'not_connected' ? 'Disconnected' : (STATUS_LABEL[connection] ?? connection)}
			</span>
		{/if}
	</header>

	{#if loading}
		<div class="flex justify-center py-8"><Spinner className="size-5" /></div>
	{:else if !data?.reachable}
		<p class="rounded-xl bg-rose-50 px-3 py-2.5 text-xs text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
			{data?.detail ?? 'WhatsApp service is not reachable'}. Start the <code>bizgpt-whatsapp</code> service and set
			<code>WHATSAPP_SERVICE_API_KEY</code> for Biz GPT.
		</p>
	{:else if account}
		<dl class="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-[0.8125rem]">
			<dt class="text-gray-500 dark:text-gray-400">Phone number</dt>
			<dd class="font-medium text-gray-800 dark:text-gray-100">{account.display_phone_number ?? 'Run Test Connection'}</dd>

			<dt class="text-gray-500 dark:text-gray-400">Business</dt>
			<dd class="text-gray-800 dark:text-gray-100">
				{account.verified_name ?? '—'}
				{#if account.business_account_id}
					<span class="text-xs text-gray-400">· WABA {account.business_account_id}</span>
				{/if}
			</dd>

			<dt class="text-gray-500 dark:text-gray-400">AI Agent</dt>
			<dd class="text-gray-800 dark:text-gray-100">{agentName}</dd>

			<dt class="text-gray-500 dark:text-gray-400">Webhook</dt>
			<dd class="text-gray-800 dark:text-gray-100">
				{#if status?.webhook}
					<span class={check(status.webhook.verify_token_set)}>
						{status.webhook.verify_token_set ? 'Verify token set' : 'Verify token missing'}
					</span>
					<span class="text-gray-300 dark:text-gray-600">·</span>
					<span class={check(status.webhook.signature_verification)}>
						{status.webhook.signature_verification ? 'Signatures verified' : 'Signatures not verified'}
					</span>
				{:else}
					—
				{/if}
			</dd>

			<dt class="text-gray-500 dark:text-gray-400">Biz GPT</dt>
			<dd class={check(status?.openwebui?.ok)}>
				{status?.openwebui?.ok ? 'Connected' : (status?.openwebui?.detail ?? 'Unknown')}
			</dd>
		</dl>

		<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
			{#each [['Contacts', account.stats.contacts], ['Received', account.stats.messages_inbound], ['Sent', account.stats.messages_outbound], ['Last 24 h', account.stats.messages_24h]] as [label, value]}
				<div class="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-850">
					<div class="text-base font-semibold text-gray-900 dark:text-gray-100">{value}</div>
					<div class="text-[11px] text-gray-500 dark:text-gray-400">{label}</div>
				</div>
			{/each}
		</div>
		{#if account.stats.messages_failed}
			<p class="mt-2 text-xs text-rose-600 dark:text-rose-400">{account.stats.messages_failed} message(s) failed to send.</p>
		{/if}

		{#if testResult}
			<div class="mt-4 space-y-1 rounded-xl bg-gray-50 px-3 py-2.5 text-xs dark:bg-gray-850">
				<div class={check(testResult.whatsapp.ok)}>
					WhatsApp API: {testResult.whatsapp.ok ? `OK (${testResult.whatsapp.verified_name ?? ''})` : testResult.whatsapp.detail}
				</div>
				<div class={check(testResult.openwebui.ok)}>
					Biz GPT: {testResult.openwebui.ok ? 'OK, agent model found' : testResult.openwebui.detail}
				</div>
			</div>
		{/if}

		{#if manage}
			<div class="mt-4 space-y-4 border-t border-gray-100 pt-4 dark:border-gray-850">
				<label class="flex flex-col gap-1.5 text-xs">
					<span class="font-medium text-gray-700 dark:text-gray-300">AI Agent that answers customers</span>
					<select
						class="rounded-lg border border-gray-200 bg-transparent px-2.5 py-1.5 text-[0.8125rem] dark:border-gray-800"
						value={account.agent_model}
						disabled={saving}
						on:change={(e) => save({ agent_model: e.currentTarget.value }, 'AI agent updated')}
					>
						{#if !$models.some((m) => m.id === account?.agent_model)}
							<option value={account.agent_model}>{account.agent_model}</option>
						{/if}
						{#each $models as model (model.id)}
							<option value={model.id}>{model.name}</option>
						{/each}
					</select>
				</label>

				<div class="flex items-center justify-between gap-3 text-xs">
					<div>
						<div class="font-medium text-gray-700 dark:text-gray-300">Auto-reply</div>
						<div class="text-gray-500 dark:text-gray-400">Off: messages are saved, nobody answers automatically.</div>
					</div>
					<Switch
						state={account.auto_reply}
						on:change={(e) => save({ auto_reply: e.detail }, e.detail ? 'Auto-reply on' : 'Auto-reply off')}
					/>
				</div>

				<div>
					<div class="mb-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">Recent conversations</div>
					{#if conversations.length === 0}
						<p class="text-xs text-gray-500 dark:text-gray-400">No conversations yet.</p>
					{:else}
						<ul class="flex flex-col">
							{#each conversations as c (c.id)}
								<li>
									<svelte:element
										this={c.openwebui_chat_id ? 'a' : 'div'}
										href={c.openwebui_chat_id ? withBasePath(`/c/${c.openwebui_chat_id}`) : undefined}
										class="flex items-center justify-between gap-3 rounded-lg px-1.5 py-1.5 text-xs {c.openwebui_chat_id
											? 'hover:bg-gray-50 dark:hover:bg-gray-850'
											: ''}"
									>
										<span class="truncate text-gray-800 dark:text-gray-100">
											{c.contact.profile_name ?? 'Customer'} <span class="text-gray-400">+{c.contact.wa_id}</span>
										</span>
										<span class="shrink-0 text-gray-500 dark:text-gray-400">
											{c.last_message_at ? timeAgo(Date.parse(c.last_message_at) / 1000) : ''}
										</span>
									</svelte:element>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</div>
		{/if}

		<footer class="mt-4 flex flex-wrap items-center gap-2">
			<button class="{button} bg-gray-900 text-white hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100" on:click={toggleManage}>
				{manage ? 'Done' : 'Manage'}
			</button>
			<button
				class="{button} flex items-center gap-1.5 border border-gray-200 text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-850"
				disabled={testing}
				on:click={runTest}
			>
				{#if testing}<Spinner className="size-3" />{/if}
				Test Connection
			</button>
			<div class="flex-1"></div>
			{#if account.is_active}
				<button
					class="{button} text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10"
					disabled={saving}
					on:click={() => (confirmDisconnect = true)}
				>
					Disconnect
				</button>
			{:else}
				<button
					class="{button} {TONES.emerald.text} hover:bg-emerald-50 dark:hover:bg-emerald-500/10"
					disabled={saving}
					on:click={() => save({ is_active: true }, 'WhatsApp reconnected')}
				>
					Reconnect
				</button>
			{/if}
		</footer>
	{/if}
</section>
