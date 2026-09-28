<script lang="ts">
	// Photo library: one folder per project and month with the approved photos and that month's PDF
	// (filed by services/monthly-report when a report is approved).
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import AuthImage from './AuthImage.svelte';
	import { api, blobUrl } from './api';

	export let monthLabel: (m: string) => string;

	const STAGE_CLS: Record<string, string> = {
		BEFORE: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300',
		DURING: 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300',
		AFTER: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300'
	};

	let months: any[] = [];
	let open: any = null;
	let loading = true;

	const base = (m: any) => `/library/${m.project_id}/${m.month}`;

	const load = async () => {
		loading = true;
		try {
			months = (await api('/library')).months;
		} catch (e) {
			toast.error((e as Error).message);
		} finally {
			loading = false;
		}
	};

	const openMonth = async (m: any) => {
		try {
			open = await api(base(m));
		} catch (e) {
			toast.error((e as Error).message);
		}
	};

	const pdf = async (download: boolean) => {
		try {
			const name = `Monthly-Report-${open.month}.pdf`;
			const url = await blobUrl(`${base(open)}/files/${name}${download ? '?download=true' : ''}`);
			if (download) {
				const a = document.createElement('a');
				a.href = url;
				a.download = `${open.project_name} - ${monthLabel(open.month)}.pdf`;
				a.click();
			} else {
				window.open(url, '_blank');
			}
			setTimeout(() => URL.revokeObjectURL(url), 60000);
		} catch (e) {
			toast.error((e as Error).message);
		}
	};

	onMount(load);
</script>

{#if open}
	<button class="text-sm text-gray-500 hover:text-gray-800 dark:hover:text-gray-200" on:click={() => (open = null)}>← All months</button>
	<div class="mt-2 flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">📁 {monthLabel(open.month)}</h1>
			<p class="text-sm text-gray-500">
				{open.project_name} · {open.photos.length} approved photo(s) · report {open.report_id}
				{#if open.approved_by}· approved by {open.approved_by} ({open.approved_at}){/if}
			</p>
		</div>
		{#if open.pdf}
			<div class="flex gap-2">
				<button class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700" on:click={() => pdf(false)}>View Report</button>
				<button class="rounded-xl border border-emerald-300 px-4 py-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300" on:click={() => pdf(true)}>Download PDF</button>
			</div>
		{/if}
	</div>
	<div class="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
		{#each open.photos as p (p.filename)}
			<div class="overflow-hidden rounded-xl border border-gray-100 bg-white dark:border-gray-800 dark:bg-gray-900">
				<AuthImage path={`${base(open)}/files/${encodeURIComponent(p.filename)}`} alt={p.filename} className="h-32 w-full object-cover" />
				<div class="space-y-1 p-2 text-xs">
					<div class="truncate font-medium text-gray-900 dark:text-gray-100">{p.filename}</div>
					<div class="flex flex-wrap gap-1">
						{#if p.stage}<span class="rounded px-1.5 py-0.5 {STAGE_CLS[p.stage] ?? ''}">{p.stage}</span>{/if}
						{#if p.location}<span class="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600 dark:bg-gray-800 dark:text-gray-300">{p.location}</span>{/if}
					</div>
					<div class="truncate text-gray-500">{p.work_type ?? 'Work type not set'}</div>
				</div>
			</div>
		{/each}
	</div>
{:else}
	<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Photo library</h1>
	<p class="mt-1 text-sm text-gray-500">Approved photos and the final report, filed in one folder per month.</p>
	{#if loading}
		<div class="flex justify-center py-16"><Spinner /></div>
	{:else if !months.length}
		<div class="mt-6 rounded-2xl border border-dashed border-gray-200 p-10 text-center text-sm text-gray-400 dark:border-gray-800">
			No approved months yet. Approve a report and its photos appear here.
		</div>
	{:else}
		<div class="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
			{#each months as m (m.project_id + m.month)}
				<button
					class="flex items-center gap-3 rounded-2xl border border-gray-100 bg-white p-4 text-left transition hover:border-orange-300 hover:shadow-sm dark:border-gray-800 dark:bg-gray-900"
					on:click={() => openMonth(m)}
				>
					<div class="text-3xl">📁</div>
					<div class="min-w-0">
						<div class="font-semibold text-gray-900 dark:text-gray-100">{monthLabel(m.month)}</div>
						<div class="truncate text-xs text-gray-500">{m.project_name}</div>
						<div class="text-xs text-gray-400">{m.photo_count} photo(s){m.pdf ? ' · PDF' : ''}</div>
					</div>
				</button>
			{/each}
		</div>
	{/if}
{/if}
