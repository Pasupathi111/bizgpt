<script lang="ts">
	// Friendly robot illustration used on the sign-in page and dashboard banner.
	export let className = 'h-28 w-24';
	const gradId = `bz-bot-${Math.random().toString(36).slice(2, 8)}`;
</script>

<svg viewBox="0 0 120 130" class={className} aria-hidden="true">
	<defs>
		<linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
			<stop offset="0" stop-color="#ffffff" />
			<stop offset="1" stop-color="#dfe4f6" />
		</linearGradient>
	</defs>
	<path d="M96 14l2.4 6.6L105 23l-6.6 2.4L96 32l-2.4-6.6L87 23l6.6-2.4L96 14Z" fill="#f97316" />
	<line x1="60" y1="10" x2="60" y2="22" stroke="#a5b4fc" stroke-width="3" stroke-linecap="round" />
	<circle cx="60" cy="8" r="4.5" fill="#818cf8" />
	<rect x="18" y="22" width="84" height="62" rx="28" fill="url(#{gradId})" stroke="#c7d2fe" stroke-width="2" />
	<rect x="30" y="34" width="60" height="38" rx="18" fill="#1e1b4b" />
	<path d="M44 55q5-7 10 0M66 55q5-7 10 0" stroke="#7dd3fc" stroke-width="4" fill="none" stroke-linecap="round" />
	<path d="M52 63q8 6 16 0" stroke="#7dd3fc" stroke-width="3" fill="none" stroke-linecap="round" />
	<rect x="10" y="44" width="10" height="20" rx="5" fill="#a5b4fc" />
	<rect x="100" y="44" width="10" height="20" rx="5" fill="#a5b4fc" />
	<rect x="36" y="88" width="48" height="34" rx="16" fill="url(#{gradId})" stroke="#c7d2fe" stroke-width="2" />
	<circle cx="60" cy="105" r="7" fill="#3b82f6" />
	<circle cx="60" cy="105" r="3" fill="#bfdbfe" />
</svg>
