import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Set VITE_NO_HMR=1 to disable hot module replacement (no browser auto-reload on save).
const hmrDisabled = process.env.VITE_NO_HMR === "1";

// Backend proxy target. Default points at the dev server on :8000.
// For e2e runs against the isolated :8001 test server, set:
//   VITE_API_TARGET=http://127.0.0.1:8001 vite --port 5174
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";
const wsTarget = apiTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: "all",
    hmr: hmrDisabled ? false : true,
    fs: {
      // Allow serving files from the repo root so public/specs symlink → docs/ works.
      allow: [".", "../.."],
    },
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/debug": {
        target: apiTarget,
        changeOrigin: true,
      },
      "/ws": {
        target: wsTarget,
        ws: true,
      },
    },
  },
});
