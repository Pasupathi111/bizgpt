<script lang="ts">
	// AI-Assisted Monthly Report Delivery (POC).
	// Upload -> AI analysis -> grouping/validation -> AI report -> human review -> approval -> PDF.
	// All state and rules live in services/monthly-report; this page only displays and edits.
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import AuthImage from './AuthImage.svelte';
	import PhotoCard from './PhotoCard.svelte';
	import { api, blobUrl } from './api';

	const STATUS: Record<string, { label: string; cls: string }> = {
		draft: { label: 'Draft', cls: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300' },
		processing: { label: 'Processing', cls: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300' },
		analyzed: { label: 'Analysed', cls: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300' },
		in_review: { label: 'In review', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' },
		rejected: { label: 'Rejected', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
		approved: { label: 'Approved', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' }
	};
	const SECTIONS = [
		['executive_summary', 'Executive Summary'],
		['location_summary', 'Location Summary'],
		['work_performed', 'Work Performed']
	];

	let cfg: any = null;
	let reports: any[] = [];
	let report: any = null;
	let loading = true;
	let error = '';
	let tab: 'photos' | 'groups' | 'report' = 'photos';

	// New report / upload
	let projectId = '';
	let month = new Date().toISOString().slice(0, 7);
	let queued: File[] = [];
	let dragging = false;
	let fileInput: HTMLInputElement;
	let busy = '';

	// Review
	let sections: Record<string, string> = {};
	let remarks = '';
	let dirty = false;
	let rejecting = false;
	let rejectReason = '';
	let poll: ReturnType<typeof setTimeout> | null = null;

	$: selectedId = $page.url.searchParams.get('report');
	$: if (cfg && selectedId !== (report?.id ?? null)) openReport(selectedId);
	$: editable = report && ['draft', 'analyzed', 'in_review', 'rejected'].includes(report.status);
	$: photoById = Object.fromEntries((report?.photos ?? []).map((p: any) => [p.id, p]));
	$: pendingCount = (report?.photos ?? []).filter((p: any) => ['pending', 'error'].includes(p.status)).length;
	$: analysedCount = (report?.photos ?? []).filter((p: any) => p.status === 'analyzed' && !p.excluded).length;

	const monthLabel = (m: string) => {
		const [y, mo] = m.split('-').map(Number);
		return new Date(y, mo - 1, 1).toLocaleString([], { month: 'long', year: 'numeric' });
	};

	const loadList = async () => {
		reports = (await api('/reports')).reports;
	};

	const setReport = (r: any, resetText = false) => {
		report = r;
		if (resetText || !dirty) {
			sections = { ...(r.content?.sections ?? {}) };
			remarks = r.remarks ?? '';
			dirty = false;
		}
		schedulePoll();
	};

	const schedulePoll = () => {
		if (poll) clearTimeout(poll);
		poll = null;
		if (report?.status === 'processing') {
			poll = setTimeout(async () => {
				try {
					const r = await api(`/reports/${report.id}`);
					setReport(r);
					if (r.status !== 'processing') {
						toast.success(`Analysis finished: ${r.progress.done ?? 0} photo(s) analysed, ${r.progress.failed ?? 0} failed.`);
						loadList();
					}
				} catch (e) {
					schedulePoll();
				}
			}, 2000);
		}
	};

	const openReport = async (id: string | null) => {
		rejecting = false;
		queued = [];
		if (!id) {
			report = null;
			return;
		}
		try {
			setReport(await api(`/reports/${id}`), true);
			tab = report.content ? 'report' : 'photos';
		} catch (e) {
			toast.error((e as Error).message);
			report = null;
		}
	};

	const select = (id: string | null) => goto(id ? `?report=${id}` : '?', { keepFocus: true, noScroll: true });

	const addFiles = (files: FileList | File[] | null) => {
		const imgs = Array.from(files ?? []).filter((f) => /^image\//.test(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name));
		const skipped = (files?.length ?? 0) - imgs.length;
		if (skipped) toast.warning(`${skipped} file(s) skipped: only JPG, PNG or WEBP photos`);
		const names = new Set(queued.map((f) => f.name + f.size));
		queued = [...queued, ...imgs.filter((f) => !names.has(f.name + f.size))];
	};

	const upload = async (rid: string) => {
		for (let i = 0; i < queued.length; i += 10) {
			const fd = new FormData();
			queued.slice(i, i + 10).forEach((f) => fd.append('files', f, f.name));
			const res = await api(`/reports/${rid}/photos`, { method: 'POST', body: fd });
			for (const r of res.rejected ?? []) toast.warning(`${r.filename}: ${r.reason}`);
		}
		queued = [];
	};

	const processPhotos = async () => {
		busy = 'process';
		try {
			let rid = report?.id;
			if (!rid) {
				if (!projectId) throw new Error('Select a project');
				if (!month) throw new Error('Select a month');
				if (!queued.length) throw new Error('Add photos first');
				rid = (await api('/reports', { method: 'POST', body: JSON.stringify({ project_id: projectId, month }) })).id;
			}
			if (queued.length) await upload(rid);
			const r = await api(`/reports/${rid}/process`, { method: 'POST' });
			await loadList();
			if (report?.id === rid) setReport(r);
			else await select(rid);
			tab = 'photos';
			toast.info('Analysing photos with the Monthly Report Vision model…');
		} catch (e) {
			toast.error((e as Error).message);
			if (report) setReport(await api(`/reports/${report.id}`));
		} finally {
			busy = '';
		}
	};

	const importGmail = async () => {
		busy = 'gmail';
		try {
			const r = await api('/gmail/import', { method: 'POST', body: JSON.stringify({ project_id: projectId, month }) });
			for (const i of r.imported) toast.success(`${i.subject}: ${i.added} photo(s) → ${i.report_id}`);
			if (r.needs_info.length) toast.warning(`${r.needs_info.length} email(s) do not name the project and month`);
			if (!r.imported.length) toast.info(`No new site-photo emails in ${r.mailbox}`);
			await loadList();
			const rid = r.reports[0] ?? r.imported[0]?.report_id;
			if (rid) await select(rid);
		} catch (e) {
			toast.error((e as Error).message);
		} finally {
			busy = '';
		}
	};

	const savePhoto = async (pid: string, body: any) => {
		try {
			setReport(await api(`/reports/${report.id}/photos/${pid}`, { method: 'PATCH', body: JSON.stringify(body) }));
		} catch (e) {
			toast.error((e as Error).message);
			throw e;
		}
	};

	const deletePhoto = async (pid: string) => {
		try {
			setReport(await api(`/reports/${report.id}/photos/${pid}`, { method: 'DELETE' }));
			loadList();
		} catch (e) {
			toast.error((e as Error).message);
		}
	};

	const run = async (name: string, fn: () => Promise<any>, ok?: string) => {
		busy = name;
		try {
			const r = await fn();
			if (r) setReport(r, true);
			if (ok) toast.success(ok);
			loadList();
		} catch (e) {
			toast.error((e as Error).message);
		} finally {
			busy = '';
		}
	};

	const generate = () => {
		if (report?.content && dirty && !confirm('Regenerating replaces your unsaved edits to the report text. Continue?')) return;
		return run('generate', async () => {
			if (dirty) await api(`/reports/${report.id}/draft`, { method: 'PUT', body: JSON.stringify({ remarks }) });
			const r = await api(`/reports/${report.id}/generate`, { method: 'POST' });
			tab = 'report';
			return r;
		}, 'Report generated. Review and edit it, then approve.');
	};

	const saveDraft = () =>
		run('save', () => api(`/reports/${report.id}/draft`, { method: 'PUT', body: JSON.stringify(report.content ? { sections, remarks } : { remarks }) }), 'Draft saved');

	const reject = () =>
		run('reject', async () => {
			// Keep the reviewer's unsaved edits; the rejection is about the saved text.
			if (dirty) await api(`/reports/${report.id}/draft`, { method: 'PUT', body: JSON.stringify({ sections, remarks }) });
			const r = await api(`/reports/${report.id}/reject`, { method: 'POST', body: JSON.stringify({ reason: rejectReason }) });
			rejecting = false;
			rejectReason = '';
			return r;
		}, 'Report rejected. Correct it and save the draft to send it back for review.');

	const approve = () =>
		run('approve', async () => {
			if (dirty) await api(`/reports/${report.id}/draft`, { method: 'PUT', body: JSON.stringify({ sections, remarks }) });
			return api(`/reports/${report.id}/approve`, { method: 'POST' });
		}, 'Report approved. PDF generated.');

	const openPdf = async (download: boolean) => {
		try {
			const url = await blobUrl(`/reports/${report.id}/pdf${download ? '?download=true' : ''}`);
			if (download) {
				const a = document.createElement('a');
				a.href = url;
				a.download = `Monthly-Report-${report.id}.pdf`;
				a.click();
			} else {
				window.open(url, '_blank');
			}
			setTimeout(() => URL.revokeObjectURL(url), 60000);
		} catch (e) {
			toast.error((e as Error).message);
		}
	};

	onMount(async () => {
		try {
			cfg = await api('/config');
			projectId = cfg.projects[0]?.id ?? '';
			await loadList();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	});
	onDestroy(() => poll && clearTimeout(poll));
</script>

<div class="flex h-full min-h-0 w-full">
	<!-- Reports list -->
	<aside class="hidden w-64 shrink-0 flex-col border-r border-gray-100 md:flex dark:border-gray-850">
		<div class="flex items-center justify-between px-4 pb-2 pt-4">
			<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">Reports</div>
			<button class="rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-medium text-white dark:bg-white dark:text-gray-900" on:click={() => select(null)}>+ New</button>
		</div>
		<div class="flex-1 overflow-y-auto px-2 pb-4">
			{#each reports as r (r.id)}
				<button
					class="mb-1 w-full rounded-lg px-3 py-2 text-left text-xs transition {report?.id === r.id ? 'bg-gray-100 dark:bg-gray-800' : 'hover:bg-gray-50 dark:hover:bg-gray-850'}"
					on:click={() => select(r.id)}
				>
					<div class="flex items-center justify-between gap-2">
						<span class="font-medium text-gray-900 dark:text-gray-100">{r.id}</span>
						<span class="rounded px-1.5 py-0.5 text-[0.65rem] {STATUS[r.status]?.cls}">{STATUS[r.status]?.label}</span>
					</div>
					<div class="mt-0.5 truncate text-gray-500">{r.project_name}</div>
					<div class="text-gray-400">{monthLabel(r.month)} · {r.photo_count} photo(s)</div>
				</button>
			{:else}
				<div class="px-3 py-6 text-center text-xs text-gray-400">No reports yet</div>
			{/each}
		</div>
	</aside>

	<main class="min-w-0 flex-1 overflow-y-auto">
		<div class="mx-auto max-w-6xl px-4 py-5 md:px-6">
			{#if loading}
				<div class="flex justify-center py-20"><Spinner /></div>
			{:else if error}
				<div class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
					Monthly Report is unavailable: {error}
				</div>
			{:else if !report}
				<!-- New report -->
				<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Monthly Report</h1>
				<p class="mt-1 text-sm text-gray-500">
					AI reads each site photo (Before / During / After, location, work, issues). You review, correct and approve before the PDF is issued.
				</p>
				<div class="mt-5 grid gap-4 rounded-2xl border border-gray-200 bg-white p-5 md:grid-cols-2 dark:border-gray-800 dark:bg-gray-900">
					<label class="flex flex-col gap-1 text-sm">
						<span class="font-medium text-gray-700 dark:text-gray-300">Project</span>
						<select class="rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700" bind:value={projectId} aria-label="Project">
							{#each cfg.projects as p}<option value={p.id}>{p.name}</option>{/each}
						</select>
					</label>
					<label class="flex flex-col gap-1 text-sm">
						<span class="font-medium text-gray-700 dark:text-gray-300">Month</span>
						<input type="month" class="rounded-lg border border-gray-200 bg-transparent px-3 py-2 dark:border-gray-700" bind:value={month} aria-label="Month" />
					</label>
					<div class="md:col-span-2">
						{@render dropZone()}
					</div>
					<div class="flex items-center justify-between md:col-span-2">
						<span class="text-xs text-gray-500">Model: {cfg.model} · review threshold {cfg.confidence_threshold}%</span>
						<div class="flex-1"></div>
						<button
							class="mr-2 rounded-xl border border-gray-200 px-4 py-2 text-sm font-semibold hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800"
							disabled={!!busy}
							title="Fetch new site-photo emails from the reports mailbox for this project and month"
							on:click={importGmail}
						>
							{busy === 'gmail' ? 'Checking Gmail…' : 'Import from Gmail'}
						</button>
						<button
							class="rounded-xl bg-orange-500 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-orange-600 disabled:opacity-50"
							disabled={!!busy || !queued.length}
							on:click={processPhotos}
						>
							{busy === 'process' ? 'Uploading…' : 'Process Photos'}
						</button>
					</div>
				</div>
			{:else}
				<!-- Report header -->
				<div class="flex flex-wrap items-start justify-between gap-3">
					<div>
						<div class="flex items-center gap-2">
							<h1 class="text-xl font-semibold text-gray-900 dark:text-gray-100">{report.project.name}</h1>
							<span class="rounded-md px-2 py-0.5 text-xs font-medium {STATUS[report.status]?.cls}">{STATUS[report.status]?.label}</span>
						</div>
						<div class="mt-0.5 text-sm text-gray-500">
							{monthLabel(report.month)} · {report.id} · {report.photos.length} photo(s) · model {report.model}
						</div>
					</div>
					<button class="text-sm text-gray-500 hover:text-gray-800 md:hidden" on:click={() => select(null)}>+ New report</button>
				</div>

				{#if report.status === 'approved'}
					<div class="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5 dark:border-emerald-500/30 dark:bg-emerald-500/10">
						<div class="text-lg font-semibold text-emerald-700 dark:text-emerald-300">✓ Report Approved</div>
						<dl class="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-4">
							<div><dt class="text-gray-500">Project</dt><dd class="text-gray-900 dark:text-gray-100">{report.project.name}</dd></div>
							<div><dt class="text-gray-500">Month</dt><dd class="text-gray-900 dark:text-gray-100">{monthLabel(report.month)}</dd></div>
							<div><dt class="text-gray-500">Approved By</dt><dd class="text-gray-900 dark:text-gray-100">{report.decision?.by}</dd></div>
							<div><dt class="text-gray-500">Approved At</dt><dd class="text-gray-900 dark:text-gray-100">{report.decision?.at}</dd></div>
						</dl>
						<div class="mt-4 flex gap-2">
							<button class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700" on:click={() => openPdf(false)}>View Report</button>
							<button class="rounded-xl border border-emerald-300 px-4 py-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300" on:click={() => openPdf(true)}>Download PDF</button>
						</div>
					</div>
				{:else if report.status === 'rejected'}
					<div class="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
						Rejected by {report.decision?.by}: “{report.decision?.reason}”. Correct the report and click Save Draft to send it back for review.
					</div>
				{/if}

				{#if report.status === 'processing'}
					{@const p = report.progress}
					<div class="mt-4 rounded-xl border border-sky-200 bg-sky-50 p-4 dark:border-sky-500/30 dark:bg-sky-500/10">
						<div class="flex items-center gap-2 text-sm font-medium text-sky-800 dark:text-sky-200">
							<Spinner className="size-4" /> Analysing photos with {report.model}: {(p.done ?? 0) + (p.failed ?? 0)} / {p.total ?? 0}
						</div>
						<div class="mt-2 h-2 overflow-hidden rounded-full bg-sky-100 dark:bg-sky-900">
							<div class="h-full bg-sky-500 transition-all" style="width: {p.total ? (100 * ((p.done ?? 0) + (p.failed ?? 0))) / p.total : 0}%"></div>
						</div>
					</div>
				{/if}

				<!-- Summary chips -->
				<div class="mt-4 flex flex-wrap gap-2 text-xs">
					<span class="rounded-lg bg-gray-100 px-2.5 py-1 dark:bg-gray-800">{analysedCount} analysed</span>
					{#if pendingCount}<span class="rounded-lg bg-gray-100 px-2.5 py-1 dark:bg-gray-800">{pendingCount} waiting / failed</span>{/if}
					<span class="rounded-lg px-2.5 py-1 {report.needs_review ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'}">
						{report.needs_review ? `⚠ ${report.needs_review} need review` : '✓ No photos need review'}
					</span>
					<span class="rounded-lg px-2.5 py-1 {report.validation.missing.length ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'}">
						{report.validation.missing.length ? `⚠ ${report.validation.missing.length} missing item(s)` : '✓ All Before/During/After present'}
					</span>
				</div>

				<!-- Tabs -->
				<div class="mt-4 flex gap-1 border-b border-gray-100 dark:border-gray-850">
					{#each [['photos', 'Photos'], ['groups', 'Grouping & Validation'], ['report', 'Report']] as [id, label]}
						<button
							class="-mb-px border-b-2 px-3 py-2 text-sm {tab === id ? 'border-orange-500 font-semibold text-gray-900 dark:text-gray-100' : 'border-transparent text-gray-500 hover:text-gray-800 dark:hover:text-gray-200'}"
							on:click={() => (tab = id as any)}>{label}</button
						>
					{/each}
				</div>

				{#if tab === 'photos'}
					{#if editable}
						<div class="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
							<div class="flex-1">{@render dropZone()}</div>
							<div class="flex flex-col gap-2">
								<button
									class="rounded-xl bg-orange-500 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-orange-600 disabled:opacity-50"
									disabled={!!busy || (!queued.length && !pendingCount)}
									on:click={processPhotos}
								>
									{busy === 'process' ? 'Uploading…' : 'Process Photos'}
								</button>
								<button
									class="rounded-xl border border-gray-200 px-4 py-2 text-sm font-semibold hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800"
									disabled={!!busy || !analysedCount}
									on:click={generate}
								>
									{busy === 'generate' ? 'Generating…' : 'Generate Monthly Report'}
								</button>
							</div>
						</div>
					{/if}
					<div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
						{#each report.photos as photo (photo.id)}
							<PhotoCard
								reportId={report.id}
								{photo}
								zones={report.project.zones}
								workTypes={report.work_types}
								stages={report.stages}
								threshold={report.threshold}
								editable={editable && report.status !== 'processing'}
								onSave={savePhoto}
								onDelete={deletePhoto}
							/>
						{/each}
					</div>
				{:else if tab === 'groups'}
					<div class="mt-4 grid gap-4 lg:grid-cols-[1fr_320px]">
						<div class="flex flex-col gap-4">
							{#each report.groups as g}
								<div class="rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
									<div class="font-semibold text-gray-900 dark:text-gray-100">{g.location}</div>
									<div class="mt-2 grid grid-cols-3 gap-3">
										{#each report.stages as s}
											<div>
												<div class="mb-1 text-xs font-medium text-gray-500">{s.charAt(0) + s.slice(1).toLowerCase()} ({g.stages[s].length})</div>
												<div class="flex flex-wrap gap-1.5">
													{#each g.stages[s] as pid}
														<AuthImage path={`/reports/${report.id}/photos/${pid}/image?size=200`} alt={photoById[pid]?.filename} className="size-16 rounded-md object-cover" />
													{:else}
														<div class="flex size-16 items-center justify-center rounded-md border border-dashed border-amber-300 text-[0.65rem] text-amber-600">missing</div>
													{/each}
												</div>
											</div>
										{/each}
									</div>
									{#if g.stages.UNKNOWN.length}
										<div class="mt-2 text-xs text-amber-700 dark:text-amber-300">{g.stages.UNKNOWN.length} photo(s) not classified</div>
									{/if}
								</div>
							{:else}
								<div class="text-sm text-gray-500">No analysed photos yet.</div>
							{/each}
						</div>
						<div class="h-fit rounded-2xl border border-gray-200 p-4 dark:border-gray-800">
							<div class="font-semibold text-gray-900 dark:text-gray-100">Missing photo check</div>
							<div class="mt-2 flex flex-col gap-3 text-sm">
								{#each report.validation.locations as loc}
									<div>
										<div class="font-medium">{loc.location}</div>
										{#each loc.checks as c}
											<div class={c.ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
												{c.ok ? '✓' : '⚠'} {c.stage.charAt(0) + c.stage.slice(1).toLowerCase()}{c.ok ? ` (${c.count})` : ' missing'}
											</div>
										{/each}
									</div>
								{/each}
								{#if report.validation.missing.some((m: string) => !m.includes(':'))}
									<div class="text-amber-700 dark:text-amber-300">
										{#each report.validation.missing.filter((m: string) => !m.includes(':')) as m}<div>⚠ {m}</div>{/each}
									</div>
								{/if}
							</div>
						</div>
					</div>
				{:else}
					<!-- Report review -->
					{#if !report.content}
						<div class="mt-6 rounded-2xl border border-dashed border-gray-300 p-8 text-center dark:border-gray-700">
							<div class="text-sm text-gray-500">No report yet. The AI writes the narrative from the reviewed photo data; photos, missing items and confidence come from the application.</div>
							<button
								class="mt-4 rounded-xl bg-orange-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
								disabled={!!busy || !analysedCount || !editable}
								on:click={generate}>{busy === 'generate' ? 'Generating…' : 'Generate Monthly Report'}</button
							>
						</div>
					{:else}
						<div class="mt-4 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
							<div class="flex flex-wrap items-baseline justify-between gap-2">
								<div>
									<div class="text-xs font-semibold uppercase tracking-wider text-orange-500">AI Generated Report · human review required</div>
									<h2 class="mt-1 text-lg font-bold text-gray-900 dark:text-gray-100">MONTHLY MAINTENANCE REPORT</h2>
									<div class="text-sm text-gray-500">Project: {report.project.name} · Month: {monthLabel(report.month)}</div>
								</div>
								<div class="text-xs text-gray-400">Generated {new Date(report.content.generated_at).toLocaleString()} by {report.content.model}</div>
							</div>

							{#each SECTIONS as [key, title]}
								{@render textSection(key, title)}
							{/each}

							{#each report.stages as s}
								<h3 class="mt-5 text-sm font-semibold text-gray-900 dark:text-gray-100">{s.charAt(0) + s.slice(1).toLowerCase()} Photos</h3>
								<div class="mt-1 flex flex-wrap gap-3">
									{#each report.groups as g}
										{#if g.stages[s].length}
											<div>
												<div class="text-xs text-gray-500">{g.location}</div>
												<div class="mt-1 flex flex-wrap gap-1.5">
													{#each g.stages[s] as pid}
														<AuthImage path={`/reports/${report.id}/photos/${pid}/image?size=200`} alt={photoById[pid]?.filename} className="size-20 rounded-md object-cover" />
													{/each}
												</div>
											</div>
										{/if}
									{/each}
								</div>
							{/each}

							{@render textSection('issues_observations', 'Issues / Observations')}

							<h3 class="mt-5 text-sm font-semibold text-gray-900 dark:text-gray-100">Missing Information</h3>
							<ul class="mt-1 text-sm text-gray-700 dark:text-gray-300">
								{#each report.validation.missing as m}<li>⚠ {m}</li>{:else}<li>✓ None. All locations have Before, During and After photos.</li>{/each}
							</ul>

							{@render textSection('remarks', 'Remarks')}
							<label class="mt-2 flex flex-col gap-1 text-sm">
								<span class="text-gray-500">Coordinator remarks</span>
								<textarea
									class="rounded-lg border border-gray-200 bg-transparent px-3 py-2 disabled:opacity-70 dark:border-gray-700"
									rows="2"
									bind:value={remarks}
									on:input={() => (dirty = true)}
									disabled={!editable}
									aria-label="Coordinator remarks"
								></textarea>
							</label>

							<h3 class="mt-5 text-sm font-semibold text-gray-900 dark:text-gray-100">AI Confidence Summary</h3>
							<table class="mt-1 w-full text-left text-sm">
								<thead class="text-xs text-gray-500"><tr><th class="py-1">Field</th><th>Avg AI confidence</th><th>Below {report.threshold}%</th><th>Unknown</th><th>Human corrected</th></tr></thead>
								<tbody>
									{#each Object.values(report.confidence.fields) as f}
										{@const ff = f as any}
										<tr class="border-t border-gray-100 dark:border-gray-850">
											<td class="py-1">{ff.label}</td>
											<td class={ff.average_ai_confidence >= report.threshold ? 'text-emerald-600' : 'text-amber-600'}>
												{ff.average_ai_confidence ?? '—'}{ff.average_ai_confidence !== null ? '%' : ''} {ff.average_ai_confidence >= report.threshold ? '✓' : '⚠'}
											</td>
											<td>{ff.below_threshold}</td><td>{ff.unknown}</td><td>{ff.human_corrected}</td>
										</tr>
									{/each}
								</tbody>
							</table>
						</div>

						{#if editable}
							<div class="sticky bottom-0 mt-4 flex flex-wrap items-center gap-2 rounded-2xl border border-gray-200 bg-white/95 p-3 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
								{#if report.approval_blockers.length && report.status === 'in_review'}
									<div class="w-full text-xs text-amber-700 dark:text-amber-300">
										Approve is blocked: {report.approval_blockers.join('; ')}.
										{#if report.needs_review}<button class="underline" on:click={() => (tab = 'photos')}>Review photos</button>{/if}
									</div>
								{/if}
								{#if rejecting}
									<input class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-gray-700" placeholder="Reason for rejection" bind:value={rejectReason} aria-label="Reason for rejection" />
									<button class="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={!!busy || rejectReason.trim().length < 3} on:click={reject}>Confirm Reject</button>
									<button class="rounded-xl px-3 py-2 text-sm text-gray-500" on:click={() => (rejecting = false)}>Cancel</button>
								{:else}
									<button class="rounded-xl border border-gray-200 px-4 py-2 text-sm font-semibold disabled:opacity-50 dark:border-gray-700" disabled={!!busy} on:click={saveDraft}>{busy === 'save' ? 'Saving…' : 'Save Draft'}</button>
									<button class="rounded-xl border border-gray-200 px-4 py-2 text-sm disabled:opacity-50 dark:border-gray-700" disabled={!!busy} on:click={generate}>{busy === 'generate' ? 'Generating…' : 'Regenerate'}</button>
									<div class="flex-1"></div>
									<button class="rounded-xl border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-600 disabled:opacity-50 dark:border-rose-500/40" disabled={!!busy || report.status !== 'in_review'} on:click={() => (rejecting = true)}>Reject</button>
									<button
										class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
										disabled={!!busy || report.status !== 'in_review' || report.approval_blockers.length > 0}
										on:click={approve}>{busy === 'approve' ? 'Approving…' : 'Approve'}</button
									>
								{/if}
							</div>
						{/if}
					{/if}
				{/if}
			{/if}
		</div>
	</main>
</div>

{#snippet textSection(key: string, title: string)}
	<label class="mt-5 flex flex-col gap-1">
		<span class="text-sm font-semibold text-gray-900 dark:text-gray-100">{title}</span>
		<textarea
			class="rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm leading-relaxed disabled:opacity-80 dark:border-gray-700"
			rows="4"
			bind:value={sections[key]}
			on:input={() => (dirty = true)}
			disabled={!editable}
			aria-label={title}
		></textarea>
	</label>
{/snippet}

{#snippet dropZone()}
	<div
		class="flex flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-6 text-center text-sm transition {dragging
			? 'border-orange-400 bg-orange-50 dark:bg-orange-500/10'
			: 'border-gray-200 dark:border-gray-700'}"
		role="button"
		tabindex="0"
		aria-label="Upload photos"
		on:dragover|preventDefault={() => (dragging = true)}
		on:dragleave={() => (dragging = false)}
		on:drop|preventDefault={(e) => {
			dragging = false;
			addFiles(e.dataTransfer?.files ?? null);
		}}
		on:click={() => fileInput.click()}
		on:keydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInput.click()}
	>
		<div class="font-medium text-gray-700 dark:text-gray-300">Drag & drop photos here, or <span class="text-orange-600 underline">browse</span></div>
		<div class="text-xs text-gray-500">JPG, PNG or WEBP · up to {cfg?.max_photos ?? 60} photos per report</div>
		{#if queued.length}
			<div class="mt-2 text-xs font-medium text-gray-700 dark:text-gray-200">{queued.length} photo(s) ready: {queued.slice(0, 4).map((f) => f.name).join(', ')}{queued.length > 4 ? '…' : ''}</div>
		{/if}
		<input
			bind:this={fileInput}
			type="file"
			accept="image/jpeg,image/png,image/webp"
			multiple
			class="hidden"
			data-testid="photo-input"
			on:change={(e) => {
				addFiles(e.currentTarget.files);
				e.currentTarget.value = '';
			}}
		/>
	</div>
{/snippet}
