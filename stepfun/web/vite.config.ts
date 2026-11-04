import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: here,
  plugins: [react()],
  server: {
    port: 5178,
    host: '127.0.0.1',
    proxy: {
      '/api': { target: 'http://127.0.0.1:5177', changeOrigin: true },
      '/models': { target: 'http://127.0.0.1:5177', changeOrigin: true },
    },
  },
  build: {
    outDir: resolve(here, 'dist'),
    emptyOutDir: true,
    // onnxruntime-web 的 wasm 较大，避免构建时被过度拆分导致 worker 加载失败
    chunkSizeWarningLimit: 4096,
  },
  worker: {
    format: 'es',
  },
});
