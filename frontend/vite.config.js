import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // Lets the install prompt/service worker show up under `npm run dev`
      // too, not just production builds -- convenient for testing, but the
      // real check before shipping is still `npm run build && npm run preview`.
      devOptions: {
        enabled: true,
      },
      // Precache the app shell; API calls to the FastAPI backend and the
      // Socket.IO connection are left alone (network-only) since lost &
      // found data needs to be live, not cached -- this PWA is about making
      // the app installable and its shell resilient to flaky campus wifi,
      // not about offline data entry.
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico}'],
        navigateFallbackDenylist: [/^\/uploads\//, /^\/socket\.io\//, /^\/reports\//, /^\/matches\//, /^\/custody\//],
      },
      manifest: {
        name: 'FindIt Campus',
        short_name: 'FindIt',
        description: 'Geo-temporal fusion matching for campus lost & found',
        start_url: '/',
        display: 'standalone',
        background_color: '#1e1e1b',
        theme_color: '#1e1e1b',
        icons: [{ src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
    }),
  ],
  server: {
    port: 5173,
  },
})