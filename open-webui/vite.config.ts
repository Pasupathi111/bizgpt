import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

import { viteStaticCopy } from 'vite-plugin-static-copy';

const backendTarget = process.env.WEBUI_BACKEND_URL || 'http://localhost:8080';

export default defineConfig({
	resolve: {
		conditions: ['onnxruntime-web-use-extern-wasm']
	},
	plugins: [
		sveltekit(),
		viteStaticCopy({
			targets: [
				{
					src: 'node_modules/onnxruntime-web/dist/*.jsep.*',

					dest: 'wasm'
				}
			]
		})
	],
	define: {
		APP_VERSION: JSON.stringify(process.env.npm_package_version),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'dev-build')
	},
	build: {
		sourcemap: true
	},
	server: {
		proxy: {
			// Dev only: Monthly Report POC service (in Docker the Biz GPT backend proxies this path).
			'/api/v1/bizgpt/monthly-report': {
				target: process.env.MONTHLY_REPORT_DEV_URL || 'http://localhost:8106',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api\/v1\/bizgpt\/monthly-report/, '/api')
			},
			'/api': {
				target: backendTarget,
				changeOrigin: true,
				ws: true
			},
			'/ollama': {
				target: backendTarget,
				changeOrigin: true
			},
			'/openai': {
				target: backendTarget,
				changeOrigin: true
			},
			'/oauth': {
				target: backendTarget,
				changeOrigin: true
			},
			'/ws': {
				target: backendTarget,
				changeOrigin: true,
				ws: true
			}
		}
	},
	worker: {
		format: 'es'
	},
	esbuild: {
		pure: process.env.ENV === 'dev' ? [] : ['console.log', 'console.debug', 'console.error']
	}
});
