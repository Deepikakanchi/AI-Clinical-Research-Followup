// vite.config.js - Vite settings for the Clinical Research Follow-up Portal frontend.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Lets files import with '@/api/client' instead of '../../api/client'
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,        // must match CORS_ORIGINS in backend/.env
    strictPort: true,  // fail instead of silently switching to another port
  },
});