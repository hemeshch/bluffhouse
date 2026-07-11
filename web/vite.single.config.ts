import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

// Single-file replay build: everything inlined into one HTML file that works
// over file://. The output replaces src/bluffhouse/viewer/template.html, into
// which render_replay() injects the payload at the /*__BLUFFHOUSE_DATA__*/
// marker (kept verbatim because it lives in a classic inline script that Vite
// never minifies).
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: "../src/bluffhouse/viewer",
    // never wipe the package dir (__init__.py lives there)
    emptyOutDir: false,
    rollupOptions: {
      input: resolve(__dirname, "template.html"),
    },
  },
});
