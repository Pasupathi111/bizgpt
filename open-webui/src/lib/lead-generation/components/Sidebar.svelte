<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import LGIcon from './LGIcon.svelte';

	/** Base path of the host app, so links to other Biz GPT pages resolve. */
	export let base = '';
	export let open = false;

	const dispatch = createEventDispatcher<{ home: void; close: void }>();
	let integrationsOpen = true;

	const top = [
		{ label: 'New Chat', icon: 'newChat', href: '/' },
		{ label: 'Search', icon: 'search', href: '/' },
		{ label: 'Dashboard', icon: 'chart', href: '/dashboard' },
		{ label: 'Dify Workflow', icon: 'grid', href: '/' }
	];
	const integrations = [
		{ label: 'WhatsApp', icon: 'chat' },
		{ label: 'Gmail', icon: 'mail' },
		{ label: 'Outlook', icon: 'inbox' },
		{ label: 'Nango', icon: 'link' }
	];
</script>

<aside class="lg-side" class:open>
	<div class="lg-brand">
		<span class="lg-brand-mark">B</span>
		Biz GPT
		<span class="lg-spacer"></span>
		<button class="lg-icon-btn sm lg-only-narrow" style="color:#c9d3f5" on:click={() => dispatch('close')} aria-label="Close menu">
			<LGIcon name="x" />
		</button>
	</div>

	<nav class="lg-side-nav">
		{#each top as item}
			<a class="lg-side-item" href={base + item.href}>
				<LGIcon name={item.icon} size={17} />
				<span class="lg-grow">{item.label}</span>
			</a>
		{/each}

		<button class="lg-side-item active" on:click={() => dispatch('home')} aria-current="page">
			<LGIcon name="target" size={17} />
			<span class="lg-grow">Lead Generation</span>
			<span class="lg-side-badge">NEW</span>
		</button>

		<a class="lg-side-item" href={base + '/'}>
			<LGIcon name="form" size={17} />
			<span class="lg-grow">Dynamic Forms</span>
		</a>

		<button class="lg-side-item" on:click={() => (integrationsOpen = !integrationsOpen)} aria-expanded={integrationsOpen}>
			<LGIcon name="puzzle" size={17} />
			<span class="lg-grow">Integrations</span>
			<span style="transition:transform .2s;transform:rotate({integrationsOpen ? 0 : -90}deg);display:flex">
				<LGIcon name="chevronDown" size={14} />
			</span>
		</button>
		{#if integrationsOpen}
			<div class="lg-side-sub">
				{#each integrations as item}
					<a class="lg-side-item" href={base + '/'}>
						<LGIcon name={item.icon} size={15} />
						<span class="lg-grow">{item.label}</span>
					</a>
				{/each}
			</div>
		{/if}

		<a class="lg-side-item" href={base + '/'}>
			<LGIcon name="inbox" size={17} />
			<span class="lg-grow">Inbox Zero</span>
		</a>
		<div class="lg-side-sep"></div>
		<a class="lg-side-item" href={base + '/admin'}>
			<LGIcon name="shield" size={17} />
			<span class="lg-grow">Admin</span>
		</a>
		<a class="lg-side-item" href={base + '/admin/settings'}>
			<LGIcon name="cog" size={17} />
			<span class="lg-grow">Settings</span>
		</a>
	</nav>

	<div class="lg-side-user">
		<span class="lg-avatar">PS</span>
		<div style="flex:1;min-width:0">
			<div style="color:#fff;font-weight:600;font-size:13px">Pasupathi S</div>
			<div style="font-size:11.5px;color:#93a3d6">Admin</div>
		</div>
		<LGIcon name="chevronDown" size={14} />
	</div>
</aside>
