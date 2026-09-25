import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // `npm run dev` proxies the API to a locally running forms service
    proxy: { '/api': 'http://localhost:8090' },
  },
})
