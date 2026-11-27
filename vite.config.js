import { defineConfig } from 'vite';

// base './' so the built game works from any static host or sub-folder
export default defineConfig({
  base: './',
  server: { port: 5173, strictPort: true },
});
