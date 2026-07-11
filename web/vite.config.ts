import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// SPA build, served by `bluffhouse serve`. Output is committed so the
// Python package works without Node (see webapp/__init__.py).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/bluffhouse/webapp/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8484",
      "/runs": "http://127.0.0.1:8484",
    },
  },
  test: {
    environment: "node",
  },
});
