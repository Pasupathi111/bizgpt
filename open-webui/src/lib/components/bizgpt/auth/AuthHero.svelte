<script lang="ts">
	// Left, decorative half of the Biz GPT sign-in page. Purely presentational.
	import { WEBUI_BASE_URL } from '$lib/constants';

	export let name = 'Biz GPT';

	const features = [
		{ title: 'AI Assistant', text: 'Get instant answers and complete tasks', icon: 'chat' },
		{ title: 'Workflow Automation', text: 'Build and run AI-powered workflows', icon: 'bolt' },
		{ title: 'Connect Your Tools', text: 'Integrate Gmail, Outlook, Dify and more', icon: 'doc' },
		{ title: 'Drive Better Results', text: 'Save time, increase productivity', icon: 'chart' }
	];

	const highlights = [
		{ value: 'AI', label: 'Models on demand', icon: 'users' },
		{ value: 'Forms', label: 'Filled from chat', icon: 'building' },
		{ value: 'Inbox', label: 'Zero, with AI', icon: 'star' }
	];

	const icons: Record<string, string> = {
		chat: 'M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z',
		bolt: 'm3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z',
		doc: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
		chart: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z',
		users: 'M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z',
		building: 'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
		star: 'M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321 .988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z'
	};

	const bars = [14, 22, 30, 42, 55, 68, 86, 100];
</script>

<aside class="bz-hero relative hidden h-full overflow-hidden text-white lg:flex lg:flex-col">
	<!-- ambient background: deep navy with a warm evening glow -->
	<div class="pointer-events-none absolute inset-0">
		<div class="absolute -right-24 -top-24 size-[42rem] rounded-full bg-orange-500/25 blur-[120px]"></div>
		<div class="absolute right-40 top-1/3 size-80 rounded-full bg-amber-300/10 blur-3xl"></div>
		<div class="absolute -bottom-40 -left-24 size-[34rem] rounded-full bg-indigo-600/30 blur-[120px]"></div>
		<div class="bz-grid absolute inset-0 opacity-[0.07]"></div>
	</div>

	<div class="relative z-10 flex h-full flex-col px-10 py-9 xl:px-16">
		<header class="flex items-center justify-between">
			<div class="flex items-center gap-3">
				<!-- LICENSE covers this Biz GPT sign-in logo.
				Do not alter, remove, obscure, or replace it except as LICENSE permits:
				https://docs.openwebui.com/license. -->
				<img
					crossorigin="anonymous"
					src="{WEBUI_BASE_URL}/static/favicon.png"
					class="size-10 rounded-xl bg-white/95 p-1"
					alt="{name} logo"
				/>
				<span class="text-2xl font-bold tracking-tight">{name}</span>
			</div>
			<div class="hidden text-xs font-medium tracking-[0.35em] text-white/70 xl:block">
				AI &nbsp;|&nbsp; AUTOMATION &nbsp;|&nbsp; PRODUCTIVITY
			</div>
		</header>

		<div class="relative mt-12 flex-1 xl:mt-16">
			<div class="relative z-10 max-w-[34rem]">
				<div
					class="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm backdrop-blur"
				>
					<svg viewBox="0 0 24 24" fill="currentColor" class="size-4 text-orange-300" aria-hidden="true">
						<path d="M12 2l1.8 5.4L19 9l-5.2 1.6L12 16l-1.8-5.4L5 9l5.2-1.6L12 2Zm6 12 .9 2.1L21 17l-2.1.9L18 20l-.9-2.1L15 17l2.1-.9L18 14Z" />
					</svg>
					Your AI-Powered Work Assistant
				</div>

				<h1 class="mt-7 text-5xl font-extrabold leading-[1.08] tracking-tight xl:text-6xl">
					<span class="whitespace-nowrap">Work Smarter</span><br />with <span class="bg-gradient-to-r from-orange-400 to-amber-300 bg-clip-text text-transparent">{name}</span>
				</h1>
				<p class="mt-6 max-w-md text-lg leading-relaxed text-white/75">
					Unify your data, automate your workflows, and get things done with AI — all in one place.
				</p>

				<ul class="mt-10 space-y-6">
					{#each features as f}
						<li class="flex items-center gap-5">
							<div
								class="flex size-14 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500/40 to-violet-500/20 ring-1 ring-white/15"
							>
								<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="size-6 text-orange-200" aria-hidden="true">
									<path stroke-linecap="round" stroke-linejoin="round" d={icons[f.icon]} />
								</svg>
							</div>
							<div>
								<div class="text-lg font-semibold">{f.title}</div>
								<div class="text-sm text-white/65">{f.text}</div>
							</div>
						</li>
					{/each}
				</ul>
			</div>

			<!-- floating product cards -->
			<div class="pointer-events-none absolute right-0 top-0 hidden h-full w-64 min-[1800px]:block">
				<div class="bz-float absolute right-0 top-20 w-60 rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur-md">
					{#each ['Analyze data', 'Generate report', 'Send email', 'Create tasks'] as task}
						<div class="flex items-center gap-3 py-1.5 text-sm">
							<span class="flex size-5 items-center justify-center rounded-md bg-emerald-500">
								<svg viewBox="0 0 20 20" fill="currentColor" class="size-3.5" aria-hidden="true"><path fill-rule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.5 7.5a1 1 0 0 1-1.4 0L3.3 9.7a1 1 0 1 1 1.4-1.4l3.8 3.8 6.8-6.8a1 1 0 0 1 1.4 0Z" clip-rule="evenodd" /></svg>
							</span>
							{task}
						</div>
					{/each}
				</div>

				<div class="bz-float-slow absolute -left-10 top-64 flex w-64 items-center gap-3 rounded-2xl border border-white/15 bg-indigo-950/60 px-4 py-3 text-sm backdrop-blur-md">
					<span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-indigo-500 shadow-lg shadow-indigo-500/40">
						<svg viewBox="0 0 24 24" fill="currentColor" class="size-4" aria-hidden="true"><path d="M12 2l1.8 5.4L19 9l-5.2 1.6L12 16l-1.8-5.4L5 9l5.2-1.6L12 2Z" /></svg>
					</span>
					Summarize today's emails and create follow-up tasks
				</div>

				<div class="bz-float absolute bottom-24 right-2 w-64 rounded-2xl border border-white/15 bg-white/10 p-5 backdrop-blur-md">
					<div class="text-sm text-white/80">Workflow activity</div>
					<div class="mt-1 flex items-center gap-1.5 text-2xl font-semibold">
						Growing
						<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 text-emerald-400" aria-hidden="true"><path d="M10 3l6 8h-4v6H8v-6H4l6-8Z" /></svg>
					</div>
					<div class="mt-4 flex h-24 items-end gap-2">
						{#each bars as h, i}
							<div
								class="flex-1 rounded-t-md {i === bars.length - 2 ? 'bg-gradient-to-t from-orange-500 to-amber-300' : 'bg-gradient-to-t from-indigo-600 to-violet-400'}"
								style="height: {h}%"
							></div>
						{/each}
					</div>
				</div>
			</div>
		</div>

		<footer class="mt-10 flex flex-wrap items-center gap-x-10 gap-y-4 border-t border-white/10 pt-7">
			{#each highlights as h}
				<div class="flex items-center gap-3">
					<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="size-8 text-orange-300" aria-hidden="true">
						<path stroke-linecap="round" stroke-linejoin="round" d={icons[h.icon]} />
					</svg>
					<div>
						<div class="text-xl font-bold leading-tight">{h.value}</div>
						<div class="text-sm text-white/60">{h.label}</div>
					</div>
				</div>
			{/each}
		</footer>
	</div>
</aside>

<style>
	.bz-hero {
		background:
			radial-gradient(120% 80% at 100% 0%, rgba(251, 146, 60, 0.18), transparent 55%),
			linear-gradient(160deg, #0b1330 0%, #0f1a3d 45%, #111436 100%);
	}
	.bz-grid {
		background-image:
			linear-gradient(rgba(255, 255, 255, 0.6) 1px, transparent 1px),
			linear-gradient(90deg, rgba(255, 255, 255, 0.6) 1px, transparent 1px);
		background-size: 48px 48px;
		mask-image: radial-gradient(70% 60% at 60% 40%, black, transparent);
	}
	.bz-float {
		animation: bz-float 7s ease-in-out infinite;
	}
	.bz-float-slow {
		animation: bz-float 9s ease-in-out infinite reverse;
	}
	@keyframes bz-float {
		0%, 100% { transform: translateY(0); }
		50% { transform: translateY(-8px); }
	}
	@media (prefers-reduced-motion: reduce) {
		.bz-float, .bz-float-slow { animation: none; }
	}
</style>
