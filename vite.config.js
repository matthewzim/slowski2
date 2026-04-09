import { defineConfig } from 'vite';

export default defineConfig({
  publicDir: 'public',
  server: {
    host: true,
    port: 5173,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
});
