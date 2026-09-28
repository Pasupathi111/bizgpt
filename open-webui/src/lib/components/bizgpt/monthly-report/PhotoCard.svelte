<script lang="ts">
	// One analysed photo: AI values with confidence, review flags, and coordinator corrections.
	import AuthImage from './AuthImage.svelte';

	export let reportId: string;
	export let photo: any;
	export let zones: string[] = [];
	export let workTypes: string[] = [];
	export let stages: string[] = [];
	export let threshold = 75;
	export let editable = true;
	export let onSave: (pid: string, body: any) => Promise<void> = async () => {};
	export let onDelete: (pid: string) => Promise<void> = async () => {};

	let editing = false;
	let busy = false;
	let form = { stage: '', location: '', work_type: '', issues: '', datetime: '' };

	$: eff = photo.effective ?? {};
	const startEdit = () => {
		form = {
			stage: eff.stage ?? '',
			location: eff.location ?? '',
			work_type: eff.work_type ?? '',
			issues: (eff.issues ?? []).join('\n'),
			datetime: eff.datetime ?? ''
		};
		editing = true;
	};

	const save = async (body: any) => {
		busy = true;
		try {
			await onSave(photo.id, body);
			editing = false;
		} finally {
			busy = false;
		}
	};

	const saveEdit = () => {
		const changed: string[] = [];
		const body: any = {};
		const cur: any = { stage: eff.stage ?? '', location: eff.location ?? '', work_type: eff.work_type ?? '', datetime: eff.datetime ?? '' };
		for (const k of ['stage', 'location', 'work_type', 'datetime']) {
			if ((form as any)[k] !== cur[k]) {
				changed.push(k);
				body[k] = (form as any)[k] || null;
			}
		}
		const issues = form.issues.split('\n').map((s) => s.trim()).filter(Boolean);
		if (issues.join('\n') !== (eff.issues ?? []).join('\n')) {
			changed.push('issues');
			body.issues = issues;
		}
		save({ ...body, fields_set: changed, reviewed: true });
	};

	const conf = (field: string) => {
		const value = eff[field];
		const c = eff[`${field}_confidence`] ?? 0;
		if (eff[`${field}_source`] === 'human') return { text: 'Human', cls: 'text-sky-600 dark:text-sky-400', icon: '✎' };
		if (!value) return { text: '—', cls: 'text-rose-600 dark:text-rose-400', icon: '⚠' };
		return c >= threshold
			? { text: `${c}%`, cls: 'text-emerald-600 dark:text-emerald-400', icon: '✓' }
			: { text: `${c}%`, cls: 'text-amber-600 dark:text-amber-400', icon: '⚠' };
	};
	const stageCls: Record<string, string> = {
		BEFORE: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
		DURING: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
		AFTER: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
	};
</script>

<div
	class="flex flex-col overflow-hidden rounded-xl border bg-white dark:bg-gray-900 {photo.excluded
		? 'border-gray-200 opacity-50 dark:border-gray-800'
		: photo.needs_review
			? 'border-amber-300 dark:border-amber-500/50'
			: 'border-gray-200 dark:border-gray-800'}"
	data-photo={photo.filename}
>
	<div class="relative">
		<AuthImage path={`/reports/${reportId}/photos/${photo.id}/image?size=480`} alt={photo.filename} className="h-40 w-full object-cover" />
		<span class="absolute left-2 top-2 rounded-md px-2 py-0.5 text-xs font-semibold {stageCls[eff.stage] ?? 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200'}">
			{eff.stage ?? (photo.status === 'analyzed' ? 'UNKNOWN' : photo.status.toUpperCase())}
		</span>
		{#if photo.reviewed}
			<span class="absolute right-2 top-2 rounded-md bg-sky-600 px-2 py-0.5 text-xs font-semibold text-white">Reviewed</span>
		{/if}
	</div>

	<div class="flex flex-1 flex-col gap-1.5 p-3 text-[0.8rem]">
		<div class="truncate font-medium text-gray-900 dark:text-gray-100" title={photo.filename}>{photo.filename}</div>

		{#if photo.status === 'pending' || photo.status === 'analyzing'}
			<div class="text-gray-500">{photo.status === 'analyzing' ? 'Analysing…' : 'Waiting for analysis'}</div>
		{:else if photo.status === 'error' && !editing}
			<div class="rounded-md bg-rose-50 p-2 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">{photo.error}</div>
		{/if}

		{#if editing}
			<label class="flex flex-col gap-0.5">
				<span class="text-gray-500">Classification</span>
				<select class="rounded-md border border-gray-200 bg-transparent px-2 py-1 dark:border-gray-700" bind:value={form.stage} aria-label="Classification">
					<option value="">Unknown</option>
					{#each stages as s}<option value={s}>{s}</option>{/each}
				</select>
			</label>
			<label class="flex flex-col gap-0.5">
				<span class="text-gray-500">Location</span>
				<select class="rounded-md border border-gray-200 bg-transparent px-2 py-1 dark:border-gray-700" bind:value={form.location} aria-label="Location">
					<option value="">Unknown</option>
					{#each zones as z}<option value={z}>{z}</option>{/each}
				</select>
			</label>
			<label class="flex flex-col gap-0.5">
				<span class="text-gray-500">Work type</span>
				<select class="rounded-md border border-gray-200 bg-transparent px-2 py-1 dark:border-gray-700" bind:value={form.work_type} aria-label="Work type">
					<option value="">Unknown</option>
					{#each workTypes as w}<option value={w}>{w}</option>{/each}
				</select>
			</label>
			<label class="flex flex-col gap-0.5">
				<span class="text-gray-500">Date / time</span>
				<input class="rounded-md border border-gray-200 bg-transparent px-2 py-1 dark:border-gray-700" bind:value={form.datetime} placeholder="Unknown" aria-label="Date / time" />
			</label>
			<label class="flex flex-col gap-0.5">
				<span class="text-gray-500">Issues (one per line)</span>
				<textarea class="rounded-md border border-gray-200 bg-transparent px-2 py-1 dark:border-gray-700" rows="2" bind:value={form.issues} aria-label="Issues"></textarea>
			</label>
			<div class="mt-1 flex gap-2">
				<button class="rounded-lg bg-gray-900 px-3 py-1 text-white disabled:opacity-50 dark:bg-white dark:text-gray-900" disabled={busy} on:click={saveEdit}>Save</button>
				<button class="rounded-lg px-3 py-1 text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800" on:click={() => (editing = false)}>Cancel</button>
			</div>
		{:else if photo.status === 'analyzed'}
			{#each [['stage', 'Classification'], ['location', 'Location'], ['work_type', 'Work']] as [field, label]}
				{@const c = conf(field)}
				<div class="flex items-center justify-between gap-2">
					<span class="text-gray-500">{label}</span>
					<span class="truncate text-right">
						<span class="text-gray-800 dark:text-gray-200">{field === 'stage' ? (eff.stage ?? 'Unknown') : (eff[field] ?? 'Unknown')}</span>
						<span class="ml-1 font-medium {c.cls}">{c.text} {c.icon}</span>
					</span>
				</div>
			{/each}
			<div class="flex items-center justify-between gap-2">
				<span class="text-gray-500">Date/time</span><span class="truncate">{eff.datetime ?? 'Unknown'}</span>
			</div>
			<div class="text-gray-500">
				Issues: <span class="text-gray-800 dark:text-gray-200">{(eff.issues ?? []).length ? eff.issues.join('; ') : 'None detected'}</span>
			</div>
			{#if eff.description}<div class="line-clamp-2 italic text-gray-500" title={eff.description}>{eff.description}</div>{/if}
		{/if}

		{#if photo.needs_review && !editing}
			<ul class="rounded-md bg-amber-50 p-2 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
				{#each photo.review_reasons as r}<li>⚠ {r}</li>{/each}
			</ul>
		{/if}

		{#if editable && !editing && photo.status !== 'pending' && photo.status !== 'analyzing'}
			<div class="mt-auto flex flex-wrap gap-1.5 pt-1">
				{#if !photo.excluded}
					<button class="rounded-lg border border-gray-200 px-2.5 py-1 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800" on:click={startEdit}>Edit</button>
					{#if photo.needs_review && photo.status === 'analyzed'}
						<button class="rounded-lg bg-emerald-600 px-2.5 py-1 text-white hover:bg-emerald-700 disabled:opacity-50" disabled={busy} on:click={() => save({ reviewed: true })}>Confirm</button>
					{/if}
					<button class="rounded-lg px-2.5 py-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" disabled={busy} on:click={() => save({ excluded: true })}>Exclude</button>
				{:else}
					<button class="rounded-lg border border-gray-200 px-2.5 py-1 dark:border-gray-700" disabled={busy} on:click={() => save({ excluded: false })}>Include again</button>
				{/if}
				<button class="ml-auto rounded-lg px-2 py-1 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10" title="Remove photo" on:click={() => onDelete(photo.id)}>Remove</button>
			</div>
		{/if}
	</div>
</div>
