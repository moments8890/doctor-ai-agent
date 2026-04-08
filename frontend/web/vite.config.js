import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Set VITE_NO_HMR=1 to disable hot module replacement (no browser auto-reload on save).
const hmrDisabled = process.env.VITE_NO_HMR === "1";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    hmr: hmrDisabled ? false : true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/debug": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});
