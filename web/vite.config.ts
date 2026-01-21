import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5174,
    open: true,
    proxy: {
      "/ws": {
        target: "ws://localhost:8765",
        ws: true,
        changeOrigin: true,
      },
      "/events": {
        target: "http://localhost:8765",
        changeOrigin: true,
      },
      "/sessions": {
        target: "http://localhost:8765",
        changeOrigin: true,
      },
      "/agents": {
        target: "http://localhost:8765",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
});
