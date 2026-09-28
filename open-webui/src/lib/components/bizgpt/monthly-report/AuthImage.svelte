<script lang="ts">
	// <img> for a photo behind the signed-in API (fetches with the Authorization header).
	import { onDestroy } from 'svelte';
	import { blobUrl } from './api';

	export let path: string;
	export let alt = '';
	export let className = '';

	let src = '';
	let loaded = '';

	$: if (path && path !== loaded) {
		loaded = path;
		blobUrl(path)
			.then((url) => {
				if (src) URL.revokeObjectURL(src);
				src = url;
			})
			.catch(() => (src = ''));
	}
	onDestroy(() => src && URL.revokeObjectURL(src));
</script>

{#if src}
	<img {src} {alt} class={className} loading="lazy" />
{:else}
	<div class="{className} animate-pulse bg-gray-100 dark:bg-gray-800"></div>
{/if}
