<script>
	import { page } from '$app/stores';
</script>

<div class="app-page-bg min-h-screen dark:bg-gray-800">
	<div class=" flex h-full">
		<div class="m-auto my-10 dark:text-gray-300 text-3xl font-normal">
			{$page.status}: {$page.error?.message}
		</div>
	</div>
</div>
