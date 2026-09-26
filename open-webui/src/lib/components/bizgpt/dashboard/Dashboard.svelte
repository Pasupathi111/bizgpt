<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import dayjs from '$lib/dayjs';
	import { user } from '$lib/stores';
	import { withBasePath } from '$lib/constants';
	import { getDashboard, type DashboardData } from '$lib/apis/bizgpt';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import ActivityChart from './ActivityChart.svelte';
	import Icon from './Icon.svelte';
	import InboxSummary from './InboxSummary.svelte';
	import IntegrationsStatus from './IntegrationsStatus.svelte';
	import Panel from './Panel.svelte';
	import RecentActivity from './RecentActivity.svelte';
	import StatCard from './StatCard.svelte';
	import { TONES, type Tone } from './tones';

	const REFRESH_MS = 60_000;
	const RANGES = [7, 14, 30];

	let data: DashboardData | null = null;
	let error: string | null = null;
	let loading = false;
	let days = 7;
	let now = dayjs();
	let timer: ReturnType<typeof setInterval>;
	let clock: ReturnType<typeof setInterval>;

	const chat = (model: string, q = '') =>
		withBasePath(`/?models=${encodeURIComponent(model)}${q ? `&q=${encodeURIComponent(q)}` : ''}`);

	async function load() {
		if (loading) return;
		loading = true;
		try {
			data = await getDashboard(localStorage.token, days);
			error = null;
		} catch (e) {
			error = typeof e === 'string' ? e : 'Could not load the dashboard.';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		load();
		timer = setInterval(() => document.visibilityState === 'visible' && load(), REFRESH_MS);
		clock = setInterval(() => (now = dayjs()), 30_000);
	});
	onDestroy(() => {
		clearInterval(timer);
		clearInterval(clock);
	});

	$: isAdmin = $user?.role === 'admin';
	$: firstName = (data?.user?.name || $user?.name || '').split(/[ @]/)[0];
	$: greeting = now.hour() < 12 ? 'Good morning' : now.hour() < 17 ? 'Good afternoon' : 'Good evening';
	$: cards = data?.cards;
	$: inboxHref = chat('bizgpt-gmail', 'Show my 10 latest emails');

	$: chartSeries = data
		? [
				{ key: 'workflow_runs', label: 'Workflow Runs', color: TONES.violet.stroke, values: data.activity.series.workflow_runs },
				{ key: 'form_submissions', label: 'Form Submissions', color: TONES.emerald.stroke, values: data.activity.series.form_submissions },
				{ key: 'messages', label: 'Messages', color: TONES.orange.stroke, values: data.activity.series.messages },
				{ key: 'tool_calls', label: 'Tool Calls', color: TONES.sky.stroke, values: data.activity.series.tool_calls }
			]
		: [];

	type Action = { label: string; icon: string; tone: Tone; href: string | null; external?: boolean; hint?: string };
	$: actions = [
		{
			label: 'Create Workflow',
			icon: 'play',
			tone: 'violet',
			href: data?.links.dify_console ?? null,
			external: true,
			hint: data?.links.dify_console ? 'Opens Dify' : 'Set DIFY_CONSOLE_URL'
		},
		{
			label: 'Create Form',
			icon: 'form',
			tone: 'emerald',
			href: isAdmin ? chat('bizgpt-form-builder') : null,
			hint: isAdmin ? 'Form Builder' : 'Admins only'
		},
		{ label: 'Connect App', icon: 'link', tone: 'orange', href: chat('bizgpt-assistant', 'Connect my Gmail') },
		{ label: 'Manage Nango', icon: 'cloud', tone: 'sky', href: chat('bizgpt-assistant', 'Show my integration status') },
		{ label: 'Open Inbox', icon: 'mail', tone: 'rose', href: inboxHref },
		{ label: 'Chat with AI', icon: 'sparkles', tone: 'violet', href: chat('bizgpt-assistant') }
	] as Action[];
</script>

<div class="mx-auto flex w-full max-w-[90rem] flex-col gap-4 px-4 pb-8 pt-3 md:px-6">
	<!-- header -->
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<div class="text-sm text-gray-500 dark:text-gray-400">Welcome back,</div>
			<h1 class="text-2xl font-semibold text-gray-900 dark:text-white">
				{greeting}{firstName ? `, ${firstName}` : ''}! 👋
			</h1>
			<p class="text-sm text-gray-500 dark:text-gray-400">
				Here's what's happening across your Biz GPT {data?.scope === 'personal' ? 'account' : 'workspace'}.
			</p>
		</div>
		<div class="flex items-center gap-3">
			<div class="flex items-center gap-2 text-right text-sm text-gray-600 dark:text-gray-300">
				<Icon name="calendar" className="size-5 text-gray-400" />
				<div>
					<div class="font-medium">{now.format('dddd, D MMM YYYY')}</div>
					<div class="text-xs text-gray-500">{now.format('h:mm A')}</div>
				</div>
			</div>
			<button
				type="button"
				class="flex size-9 items-center justify-center rounded-xl border border-gray-100 bg-white text-gray-500 transition hover:text-gray-800 dark:border-gray-850 dark:bg-gray-900 dark:hover:text-gray-100"
				on:click={load}
				aria-label="Refresh dashboard"
				title="Refresh"
			>
				<Icon name="refresh" className="size-4 {loading ? 'animate-spin' : ''}" strokeWidth="2" />
			</button>
		</div>
	</div>

	{#if !data && !error}
		<div class="flex h-64 items-center justify-center"><Spinner className="size-5" /></div>
	{:else if !data && error}
		<div class="rounded-2xl border border-rose-100 bg-rose-50 p-6 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
			{error}
			<button class="ml-2 font-medium underline" on:click={load}>Retry</button>
		</div>
	{:else if data && cards}
		{#if error}
			<div class="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
				Showing the last loaded data: {error}
			</div>
		{/if}

		<!-- stat cards -->
		<div class="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-5">
			<StatCard title="Dify Workflows" icon="workflow" tone="violet"
				value={cards.workflows.available ? cards.workflows.active : '—'}
				caption={cards.workflows.available ? `Active of ${cards.workflows.total} workflows` : 'Workflows API unavailable'}
				href={data.links.dify_console} external />
			<StatCard title="Dynamic Forms" icon="form" tone="emerald"
				value={cards.forms.available ? cards.forms.types : '—'}
				caption={`${cards.forms.submissions} submitted · ${cards.forms.custom} custom`}
				href={isAdmin ? chat('bizgpt-form-builder', 'List all forms') : chat('bizgpt-assistant')} />
			<StatCard title="Integrations" icon="link" tone="orange"
				value={`${cards.integrations.connected}/${cards.integrations.total}`}
				caption="Connected services"
				href={isAdmin ? withBasePath('/admin/settings/tools') : null} />
			<StatCard title="Nango" icon="cloud" tone="sky"
				value={cards.nango.up ? cards.nango.connections : 'Down'}
				muted={!cards.nango.up}
				caption={cards.nango.up ? 'Personal connections' : 'OAuth broker offline'}
				href={chat('bizgpt-assistant', 'Show my integration status')} />
			<StatCard title="Inbox Zero" icon="mail" tone="rose"
				value={cards.inbox.available ? `${cards.inbox.unread}${cards.inbox.unread_capped ? '+' : ''}` : '—'}
				muted={!cards.inbox.available}
				caption={cards.inbox.available ? 'Unread messages' : cards.inbox.reason === 'restricted' ? 'Admins only' : 'Mailbox unavailable'}
				href={cards.inbox.available ? inboxHref : null} />
		</div>

		<!-- chart + quick actions -->
		<div class="grid grid-cols-1 gap-3 lg:grid-cols-3">
			<Panel title="Activity Overview" subtitle="Workflow runs, form submissions, messages and tool calls"
				icon="chart" tone="violet" className="lg:col-span-2">
				<svelte:fragment slot="action">
					<select
						bind:value={days}
						on:change={load}
						class="rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
						aria-label="Date range"
					>
						{#each RANGES as r}<option value={r}>Last {r} days</option>{/each}
					</select>
				</svelte:fragment>
				<ActivityChart days={data.activity.days} series={chartSeries} />
			</Panel>

			<Panel title="Quick Actions" subtitle="Get started with common tasks" icon="bolt" tone="orange">
				<div class="grid flex-1 grid-cols-2 gap-2.5 sm:grid-cols-3">
					{#each actions as a (a.label)}
						<svelte:element
							this={a.href ? 'a' : 'div'}
							href={a.href ?? undefined}
							target={a.href && a.external ? '_blank' : undefined}
							rel={a.href && a.external ? 'noopener noreferrer' : undefined}
							title={a.hint}
							class="group flex min-h-24 flex-col justify-between rounded-xl p-3 transition {TONES[a.tone].soft} {a.href
								? ''
								: 'cursor-not-allowed opacity-50'}"
						>
							<div class="flex size-8 items-center justify-center rounded-lg bg-white/80 dark:bg-gray-900/60 {TONES[a.tone].text}">
								<Icon name={a.icon} className="size-4" />
							</div>
							<div class="flex items-end justify-between gap-1">
								<span class="text-xs font-medium text-gray-800 dark:text-gray-100">{a.label}</span>
								<Icon name="arrow" className="size-3.5 shrink-0 {TONES[a.tone].text} transition group-hover:translate-x-0.5" strokeWidth="2" />
							</div>
						</svelte:element>
					{/each}
				</div>
			</Panel>
		</div>

		<!-- bottom row -->
		<div class="grid grid-cols-1 gap-3 lg:grid-cols-3">
			<RecentActivity items={data.recent_activity} />
			<IntegrationsStatus items={data.integrations} manageHref={isAdmin ? withBasePath('/admin/settings/tools') : null} />
			<InboxSummary inbox={data.inbox} reason={cards.inbox.reason} openHref={inboxHref} />
		</div>

		<div class="text-center text-[11px] text-gray-400">
			Updated {dayjs.unix(data.generated_at).format('h:mm:ss A')} · refreshes every minute
		</div>
	{/if}
</div>
