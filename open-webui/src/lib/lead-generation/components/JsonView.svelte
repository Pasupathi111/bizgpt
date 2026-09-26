<script lang="ts">
	// Read-only, syntax-highlighted JSON block.
	export let value: unknown;
	export let maxHeight = 260;

	const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

	$: html = esc(JSON.stringify(value, null, 2) ?? 'null').replace(
		/("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g,
		(m, str, colon, lit, num) => {
			if (str) return colon ? `<span class="k">${str}</span>${colon}` : `<span class="s">${str}</span>`;
			if (lit) return `<span class="l">${lit}</span>`;
			if (num) return `<span class="n">${num}</span>`;
			return m;
		}
	);
</script>

<pre class="json" style="max-height:{maxHeight}px">{@html html}</pre>

<style>
	.json {
		margin: 0;
		padding: 10px 12px;
		background: #f8fafc;
		border: 1px solid #e6e9f0;
		border-radius: 8px;
		font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
		font-size: 11.5px;
		line-height: 1.55;
		color: #334155;
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
	}
	.json :global(.k) {
		color: #b42318;
	}
	.json :global(.s) {
		color: #1d4ed8;
	}
	.json :global(.n) {
		color: #c2410c;
	}
	.json :global(.l) {
		color: #7c3aed;
	}
</style>
