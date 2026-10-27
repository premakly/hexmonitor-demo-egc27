import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The dev server proxies /api to the demo backend, so the browser only ever
// talks to one origin. Point DEMO_BACKEND elsewhere if the backend does not
// run on this machine's port 8000.

// The tests build dates without a time zone and expect UTC. Set here, in the
// main process, so every test worker inherits it; only under Vitest.
if (process.env.VITEST) process.env.TZ = 'UTC'

const backend = process.env.DEMO_BACKEND || 'http://127.0.0.1:8000'

// Served under a sub-path on GitHub Pages (https://<account>.github.io/<repo>/):
// DEMO_BASE gives it at build time; at the root otherwise.
const base = process.env.DEMO_BASE || '/'

export default defineConfig({
  base,
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { '/api': { target: backend, changeOrigin: true } }
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.js'],
    setupFiles: ['tests/setup.js']
  }
})
