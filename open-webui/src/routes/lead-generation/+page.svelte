<script lang="ts">
	// Standalone route for the Lead Generation module. It lives outside the (app)
	// group so it renders its own BizGPT shell and leaves existing pages untouched.
	import { base } from '$app/paths';
	import LeadGenerationApp from '$lib/lead-generation/LeadGenerationApp.svelte';
</script>

<svelte:head>
	<title>Lead Generation · Biz GPT</title>
</svelte:head>

<LeadGenerationApp {base} />
