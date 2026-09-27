<script lang="ts">
	// Biz Inbox > Orders: T-shirt orders from customer emails (and the T-Shirt Orders chat),
	// served by services/orders at /bizgpt-orders. Approve / Reject are admin-only (enforced server-side).
	import { onDestroy, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const API = '/bizgpt-orders/api';

	const STATUSES = [
		{ id: 'new', emoji: '📥', label: 'New Orders' },
		{ id: 'missing_info', emoji: '⚠️', label: 'Missing Information' },
		{ id: 'awaiting_customer', emoji: '🕐', label: 'Awaiting Customer Response' },
		{ id: 'ready_for_approval', emoji: '🔍', label: 'Ready for Approval' },
		{ id: 'approved', emoji: '✅', label: 'Approved' },
		{ id: 'processing', emoji: '📦', label: 'Processing' },
		{ id: 'rejected', emoji: '❌', label: 'Rejected' }
	];
	const statusMeta = Object.fromEntries(STATUSES.map((s) => [s.id, s]));
	const badgeClass: Record<string, string> = {
		new: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
		missing_info: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
		awaiting_customer: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300',
		ready_for_approval: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300',
		approved: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
		processing: 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300',
		rejected: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300'
	};
	const EVENT_LABELS: Record<string, string> = {
		order_created: 'Order created',
		validated: 'Validated',
		missing_info_requested: 'Asked customer for missing details',
		customer_replied: 'Customer replied',
		customer_wrote_after_decision: 'Customer wrote after the decision',
		missing_info_limit: 'Stopped asking the customer',
		approved: 'Approved',
		confirmation_sent: 'Confirmation emailed',
		processing_started: 'Processing started',
		rejected: 'Rejected',
		rejection_sent: 'Rejection emailed',
		email_failed: 'Email failed',
		email_skipped: 'Email skipped'
	};

	let filter = '';
	let orders: any[] = [];
	let counts: Record<string, number> = {};
	let canDecide = false;
	let selected: any = null;
	let loading = true;
	let error = '';
	let busy = false;
	let rejecting = false;
	let reason = '';
	let timer: ReturnType<typeof setInterval>;

	const api = async (path: string, init: RequestInit = {}) => {
		const res = await fetch(`${API}${path}`, {
			...init,
			headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.token ?? ''}`, ...(init.headers ?? {}) }
		});
		const data = await res.json().catch(() => ({}));
		if (!res.ok) throw new Error(data?.detail ?? `Request failed (${res.status})`);
		return data;
	};

	const load = async () => {
		try {
			const data = await api(`/orders${filter ? `?status=${filter}` : ''}`);
			orders = data.orders;
			counts = data.counts;
			canDecide = data.can_decide;
			error = '';
			if (selected) await open(selected.id, true);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	};

	const open = async (id: string, quiet = false) => {
		try {
			selected = await api(`/orders/${id}`);
			if (!quiet) {
				rejecting = false;
				reason = '';
			}
		} catch (e) {
			if (!quiet) toast.error((e as Error).message);
		}
	};

	const decide = async (action: 'approve' | 'reject' | 'resend-confirmation') => {
		if (!selected || busy) return;
		busy = true;
		try {
			const body = action === 'reject' ? JSON.stringify({ reason }) : undefined;
			selected = { ...(await api(`/orders/${selected.id}/${action}`, { method: 'POST', body })), can_decide: canDecide };
			toast.success(
				action === 'reject' ? `Order ${selected.reference} rejected; customer notified.` : `Order ${selected.reference} approved; confirmation sent.`
			);
			rejecting = false;
			reason = '';
		} catch (e) {
			toast.error((e as Error).message);
		} finally {
			busy = false;
			await load();
		}
	};

	const setFilter = (id: string) => {
		filter = filter === id ? '' : id;
		loading = true;
		load();
	};

	const itemsSummary = (o: any) =>
		(o.fields.items ?? [])
			.map((i: any) => `${i.quantity ?? '?'} × ${[i.color, i.size].filter(Boolean).join(' ') || 'T-shirt'}`)
			.join(', ') || 'No items yet';
	const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

	$: failedConfirmation =
		selected?.status === 'approved' && (selected?.events ?? []).some((e: any) => e.type === 'email_failed');

	onMount(() => {
		load();
		timer = setInterval(load, 30000);
	});
	onDestroy(() => clearInterval(timer));
</script>

<div class="flex h-full min-h-0 flex-col">
	<!-- Status filters -->
	<div class="flex gap-2 overflow-x-auto border-b border-gray-100 px-4 py-2.5 dark:border-gray-850">
		{#each STATUSES as s}
			<button
				type="button"
				on:click={() => setFilter(s.id)}
				class="flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition {filter === s.id
					? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900'
					: 'border-gray-200 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-850'}"
			>
				<span>{s.emoji}</span>{s.label}
				<span class="rounded-full bg-black/5 px-1.5 text-[11px] dark:bg-white/10">{counts[s.id] ?? 0}</span>
			</button>
		{/each}
	</div>

	{#if loading && !orders.length}
		<div class="flex flex-1 items-center justify-center"><Spinner className="size-5" /></div>
	{:else if error}
		<div class="flex flex-1 items-center justify-center p-6 text-sm text-gray-500">{error}</div>
	{:else}
		<div class="flex min-h-0 flex-1 flex-col md:flex-row">
			<!-- Order list -->
			<div
				class="min-h-0 overflow-y-auto border-gray-100 dark:border-gray-850 md:w-80 md:shrink-0 md:border-r {selected
					? 'hidden md:block'
					: 'flex-1 md:flex-none'}"
			>
				{#if !orders.length}
					<p class="p-6 text-center text-sm text-gray-500">
						No orders{filter ? ` in “${statusMeta[filter].label}”` : ' yet'}. Customers can email their T-shirt orders to
						dbizgpt.assistant@gmail.com.
					</p>
				{/if}
				{#each orders as o (o.id)}
					<button
						type="button"
						on:click={() => open(o.id)}
						class="block w-full border-b border-gray-100 px-4 py-3 text-left transition hover:bg-gray-50 dark:border-gray-850 dark:hover:bg-gray-850 {selected?.id ===
						o.id
							? 'bg-gray-50 dark:bg-gray-850'
							: ''}"
					>
						<div class="flex items-center justify-between gap-2">
							<span class="text-sm font-semibold text-gray-900 dark:text-gray-100">{o.reference}</span>
							<span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium {badgeClass[o.status]}"
								>{statusMeta[o.status]?.emoji} {statusMeta[o.status]?.label}</span
							>
						</div>
						<div class="mt-1 truncate text-xs text-gray-600 dark:text-gray-300">
							{o.fields.customer_name ?? o.fields.customer_email ?? 'Unknown customer'} · {itemsSummary(o)}
						</div>
						<div class="mt-0.5 text-[11px] text-gray-400">
							{o.source === 'chat' ? 'Chat form' : 'Email'} · {when(o.updated_at)}{o.validation.missing.length
								? ` · ${o.validation.missing.length} missing`
								: ''}
						</div>
					</button>
				{/each}
			</div>

			<!-- Order detail -->
			<div class="min-h-0 flex-1 overflow-y-auto {selected ? '' : 'hidden md:block'}">
				{#if !selected}
					<div class="flex h-full items-center justify-center p-6 text-sm text-gray-500">Select an order to see its details.</div>
				{:else}
					<div class="mx-auto max-w-3xl space-y-5 p-4 md:p-6">
						<button type="button" class="text-xs text-gray-500 underline md:hidden" on:click={() => (selected = null)}
							>← All orders</button
						>
						<div class="flex flex-wrap items-start justify-between gap-3">
							<div>
								<div class="text-xs font-semibold uppercase tracking-wide text-gray-500">
									T-shirt order · {selected.source === 'chat' ? 'Biz GPT chat' : 'Email'}
								</div>
								<h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{selected.reference}</h2>
								{#if selected.subject}<div class="text-xs text-gray-500">{selected.subject}</div>{/if}
							</div>
							<span class="rounded-full px-3 py-1 text-xs font-semibold {badgeClass[selected.status]}"
								>{statusMeta[selected.status]?.emoji} {statusMeta[selected.status]?.label}</span
							>
						</div>

						<!-- Validation -->
						<section class="rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
							<div class="mb-3 flex items-center justify-between">
								<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Validation</h3>
								<span class="text-xs {selected.validation.complete ? 'text-emerald-600' : 'text-amber-600'}">
									{selected.validation.complete ? 'Complete' : `${selected.validation.missing.length} missing`}
								</span>
							</div>
							<div class="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
								{#each selected.validation.checks as c}
									<div class="flex items-center gap-2 text-sm">
										<span>{c.ok ? '✅' : '❌'}</span>
										<span class={c.ok ? 'text-gray-700 dark:text-gray-200' : 'font-medium text-rose-600 dark:text-rose-400'}>{c.label}</span>
									</div>
								{/each}
							</div>
						</section>

						<!-- Details -->
						<section class="rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
							<h3 class="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Order details</h3>
							<dl class="grid grid-cols-[minmax(110px,34%)_1fr] gap-x-4 gap-y-1.5 text-sm">
								{#each [['Customer', 'customer_name'], ['Email', 'customer_email'], ['Phone', 'customer_phone'], ['Delivery address', 'delivery_address'], ['Preferred delivery time', 'preferred_delivery_time'], ['Payment method', 'payment_method'], ['Notes', 'notes']] as [label, key]}
									<dt class="text-gray-500">{label}</dt>
									<dd class="break-words font-medium text-gray-900 dark:text-gray-100">{selected.fields[key] ?? '—'}</dd>
								{/each}
							</dl>
							<div class="mt-4 overflow-x-auto">
								<table class="w-full text-sm">
									<thead>
										<tr class="border-b border-gray-200 text-left text-xs text-gray-500 dark:border-gray-800">
											<th class="py-1.5 pr-3 font-medium">Qty</th><th class="py-1.5 pr-3 font-medium">Colour</th>
											<th class="py-1.5 pr-3 font-medium">Size</th><th class="py-1.5 font-medium">Print</th>
										</tr>
									</thead>
									<tbody>
										{#each selected.fields.items ?? [] as i}
											<tr class="border-b border-gray-100 dark:border-gray-850">
												<td class="py-1.5 pr-3">{i.quantity ?? '—'}</td><td class="py-1.5 pr-3">{i.color ?? '—'}</td>
												<td class="py-1.5 pr-3">{i.size ?? '—'}</td><td class="py-1.5">{i.print_text ?? '—'}</td>
											</tr>
										{:else}
											<tr><td colspan="4" class="py-2 text-gray-500">No items yet</td></tr>
										{/each}
									</tbody>
								</table>
							</div>
						</section>

						<!-- Decision -->
						{#if selected.status === 'ready_for_approval'}
							<section class="rounded-2xl border border-violet-200 bg-violet-50/40 p-4 dark:border-violet-500/30 dark:bg-violet-500/5">
								<h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Ready for approval</h3>
								{#if selected.confirmation_preview}
									<details class="mt-2 text-sm">
										<summary class="cursor-pointer text-xs text-gray-600 dark:text-gray-300"
											>Confirmation email to {selected.confirmation_preview.to}</summary
										>
										<div class="mt-2 rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900">
											<div class="text-xs text-gray-500">Subject: {selected.confirmation_preview.subject}</div>
											<pre class="mt-2 whitespace-pre-wrap font-sans text-[13px] text-gray-800 dark:text-gray-200">{selected.confirmation_preview.body}</pre>
										</div>
									</details>
								{/if}
								{#if canDecide}
									{#if rejecting}
										<textarea
											bind:value={reason}
											rows="3"
											placeholder="Reason for rejecting (emailed to the customer)"
											class="mt-3 w-full rounded-xl border border-rose-300 bg-white p-2.5 text-sm outline-none focus:ring-2 focus:ring-rose-300 dark:border-rose-500/40 dark:bg-gray-900"
										></textarea>
										<div class="mt-2 flex gap-2">
											<button
												type="button"
												disabled={busy || reason.trim().length < 3}
												on:click={() => decide('reject')}
												class="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
												>{busy ? 'Rejecting…' : 'Confirm reject'}</button
											>
											<button
												type="button"
												on:click={() => ((rejecting = false), (reason = ''))}
												class="rounded-xl border border-gray-300 px-4 py-2 text-sm dark:border-gray-700">Cancel</button
											>
										</div>
									{:else}
										<div class="mt-3 flex flex-wrap gap-2">
											<button
												type="button"
												disabled={busy}
												on:click={() => decide('approve')}
												class="rounded-xl bg-green-600 px-5 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
												>{busy ? 'Approving…' : 'Approve Order'}</button
											>
											<button
												type="button"
												disabled={busy}
												on:click={() => (rejecting = true)}
												class="rounded-xl bg-red-600 px-5 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
												>Reject Order</button
											>
										</div>
									{/if}
								{:else}
									<p class="mt-2 text-xs text-gray-500">Only Biz GPT admins can approve or reject orders.</p>
								{/if}
							</section>
						{:else if canDecide && ['new', 'missing_info', 'awaiting_customer'].includes(selected.status)}
							<section class="rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
								<p class="text-sm text-gray-600 dark:text-gray-300">
									Waiting for the customer's details. It moves to Ready for Approval automatically once they reply.
								</p>
								{#if rejecting}
									<textarea
										bind:value={reason}
										rows="3"
										placeholder="Reason for rejecting (emailed to the customer)"
										class="mt-3 w-full rounded-xl border border-rose-300 bg-white p-2.5 text-sm dark:border-rose-500/40 dark:bg-gray-900"
									></textarea>
									<div class="mt-2 flex gap-2">
										<button
											type="button"
											disabled={busy || reason.trim().length < 3}
											on:click={() => decide('reject')}
											class="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
											>Confirm reject</button
										>
										<button type="button" on:click={() => ((rejecting = false), (reason = ''))} class="rounded-xl border border-gray-300 px-4 py-2 text-sm dark:border-gray-700"
											>Cancel</button
										>
									</div>
								{:else}
									<button
										type="button"
										on:click={() => (rejecting = true)}
										class="mt-3 rounded-xl border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-500/40 dark:hover:bg-red-500/10"
										>Reject Order</button
									>
								{/if}
							</section>
						{:else if failedConfirmation && canDecide}
							<section class="rounded-2xl border border-amber-200 bg-amber-50/50 p-4 dark:border-amber-500/30 dark:bg-amber-500/5">
								<p class="text-sm text-amber-800 dark:text-amber-300">Approved, but the confirmation email failed to send.</p>
								<button
									type="button"
									disabled={busy}
									on:click={() => decide('resend-confirmation')}
									class="mt-2 rounded-xl bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-50"
									>Retry confirmation email</button
								>
							</section>
						{/if}

						<!-- History -->
						<section class="rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
							<h3 class="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">History</h3>
							<ol class="space-y-3 border-l border-gray-200 pl-4 dark:border-gray-800">
								{#each [...(selected.events ?? [])].reverse() as e}
									<li class="relative text-sm">
										<span class="absolute -left-[21px] top-1.5 size-2 rounded-full {e.type.includes('fail') || e.type === 'rejected'
												? 'bg-rose-500'
												: e.type.includes('sent') || e.type === 'approved'
													? 'bg-emerald-500'
													: 'bg-gray-400'}"
										></span>
										<div class="font-medium text-gray-900 dark:text-gray-100">{EVENT_LABELS[e.type] ?? e.type}</div>
										<div class="text-xs text-gray-500">{when(e.at)} · {e.actor}</div>
										{#if e.detail?.reason}<div class="mt-0.5 text-xs text-gray-700 dark:text-gray-300">Reason: {e.detail.reason}</div>{/if}
										{#if e.detail?.missing?.length}<div class="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
												Missing: {e.detail.missing.join(', ')}
											</div>{/if}
										{#if e.detail?.to}<div class="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
												To {e.detail.to}{e.detail.gmail_message_id ? ` · Gmail ${e.detail.gmail_message_id}` : ''}
											</div>{/if}
										{#if e.detail?.excerpt}<div class="mt-1 line-clamp-3 whitespace-pre-wrap rounded-lg bg-gray-50 p-2 text-xs text-gray-600 dark:bg-gray-850 dark:text-gray-300">
												{e.detail.excerpt}
											</div>{/if}
										{#if e.detail?.error}<div class="mt-0.5 text-xs text-rose-600">{e.detail.error}</div>{/if}
									</li>
								{/each}
							</ol>
						</section>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
