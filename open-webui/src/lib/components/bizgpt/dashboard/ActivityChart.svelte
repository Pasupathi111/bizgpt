<script lang="ts">
	import dayjs from '$lib/dayjs';

	export let days: string[] = [];
	export let series: { key: string; label: string; color: string; values: number[] }[] = [];

	let width = 600;
	const height = 240;
	const pad = { top: 12, right: 12, bottom: 28, left: 32 };
	let hidden: Record<string, boolean> = {};
	let hover: number | null = null;

	$: visible = series.filter((s) => !hidden[s.key]);
	$: rawMax = Math.max(1, ...visible.flatMap((s) => s.values));
	$: step = niceStep(rawMax / 4);
	$: yMax = Math.max(step * 4, step);
	$: ticks = Array.from({ length: 5 }, (_, i) => i * (yMax / 4));
	$: innerW = Math.max(10, width - pad.left - pad.right);
	$: innerH = height - pad.top - pad.bottom;
	$: x = (i: number) => pad.left + (days.length <= 1 ? innerW / 2 : (i * innerW) / (days.length - 1));
	$: y = (v: number) => pad.top + innerH - (v / yMax) * innerH;
	$: labelEvery = Math.ceil(days.length / Math.max(2, Math.floor(innerW / 64)));

	function niceStep(raw: number) {
		const exp = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1))));
		const f = raw / exp;
		return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * exp;
	}

	// Reactive (not plain functions) so paths redraw when x/y scales change on resize or range change.
	// Smoothing: cubic Bézier through points with horizontal tangents.
	$: path = (values: number[]) => {
		if (!values.length) return '';
		let d = `M ${x(0)} ${y(values[0])}`;
		for (let i = 1; i < values.length; i++) {
			const x0 = x(i - 1), x1 = x(i), mx = (x0 + x1) / 2;
			d += ` C ${mx} ${y(values[i - 1])}, ${mx} ${y(values[i])}, ${x1} ${y(values[i])}`;
		}
		return d;
	};

	$: area = (values: number[]) =>
		values.length ? `${path(values)} L ${x(values.length - 1)} ${y(0)} L ${x(0)} ${y(0)} Z` : '';

	function onMove(e: MouseEvent) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const px = e.clientX - rect.left - pad.left;
		const i = Math.round((px / innerW) * (days.length - 1));
		hover = i >= 0 && i < days.length ? i : null;
	}
</script>

<div class="relative w-full" bind:clientWidth={width}>
	<svg {width} {height} class="block overflow-visible" role="img" aria-label="Activity over time"
		on:mousemove={onMove} on:mouseleave={() => (hover = null)}>
		<defs>
			{#each series as s}
				<linearGradient id="bz-grad-{s.key}" x1="0" x2="0" y1="0" y2="1">
					<stop offset="0%" stop-color={s.color} stop-opacity="0.18" />
					<stop offset="100%" stop-color={s.color} stop-opacity="0" />
				</linearGradient>
			{/each}
		</defs>

		{#each ticks as t}
			<line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)}
				class="stroke-gray-100 dark:stroke-gray-800" stroke-dasharray={t === 0 ? '' : '3 4'} />
			<text x={pad.left - 8} y={y(t)} dy="0.32em" text-anchor="end"
				class="fill-gray-400 text-[10px] tabular-nums">{Math.round(t)}</text>
		{/each}

		{#each days as d, i}
			{#if i % labelEvery === 0 || i === days.length - 1}
				<text x={x(i)} y={height - 8} text-anchor="middle" class="fill-gray-400 text-[10px]">
					{dayjs(d).format('D MMM')}
				</text>
			{/if}
		{/each}

		{#each visible as s, idx (s.key)}
			{#if idx === 0}
				<path d={area(s.values)} fill="url(#bz-grad-{s.key})" />
			{/if}
			<path d={path(s.values)} fill="none" stroke={s.color} stroke-width="2.25"
				stroke-linecap="round" stroke-linejoin="round" />
		{/each}

		{#if hover !== null}
			<line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + innerH}
				class="stroke-gray-300 dark:stroke-gray-700" />
			{#each visible as s}
				<circle cx={x(hover)} cy={y(s.values[hover] ?? 0)} r="3.5" fill={s.color}
					class="stroke-white dark:stroke-gray-900" stroke-width="2" />
			{/each}
		{/if}
	</svg>

	{#if hover !== null}
		<div
			class="pointer-events-none absolute top-2 z-10 min-w-36 rounded-xl border border-gray-100 bg-white/95 px-3 py-2 text-xs shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-900/95"
			style="left: {Math.min(Math.max(x(hover) - 72, 0), Math.max(width - 160, 0))}px"
		>
			<div class="mb-1 font-medium text-gray-700 dark:text-gray-200">
				{dayjs(days[hover]).format('ddd, D MMM')}
			</div>
			{#each visible as s}
				<div class="flex items-center justify-between gap-4 text-gray-600 dark:text-gray-300">
					<span class="flex items-center gap-1.5">
						<span class="size-2 rounded-full" style="background:{s.color}"></span>{s.label}
					</span>
					<span class="tabular-nums font-medium">{s.values[hover] ?? 0}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<div class="mt-2 flex flex-wrap justify-center gap-x-5 gap-y-1">
	{#each series as s (s.key)}
		<button
			type="button"
			class="flex items-center gap-1.5 text-xs transition {hidden[s.key]
				? 'text-gray-400 line-through'
				: 'text-gray-600 dark:text-gray-300'}"
			on:click={() => (hidden = { ...hidden, [s.key]: !hidden[s.key] })}
			aria-pressed={!hidden[s.key]}
		>
			<span class="size-2 rounded-full" style="background:{s.color}"></span>
			{s.label}
		</button>
	{/each}
</div>
