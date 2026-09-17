import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxies API calls to the backend during local dev, so the browser
    // never makes a cross-origin request - no CORS middleware needed on
    // the FastAPI side. Run `uvicorn backend.main:app` on 8000 alongside
    // `npm run dev` here.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
