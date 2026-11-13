import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

const root = path.resolve(__dirname);

export default defineConfig({
  root,
  plugins: [react()],
  build: {
    outDir: path.resolve(root, 'dist/renderer'),
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        main: path.resolve(root, 'index.html'),
      },
    },
  },
  server: {
    port: 5173,
  },
  resolve: {
    alias: {
      '@shared': path.resolve(root, 'src/shared'),
      '@core': path.resolve(root, 'src/core'),
      '@renderer': path.resolve(root, 'src/renderer'),
    },
  },
});
