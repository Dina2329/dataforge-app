/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // react-grid-layout (and some of its transitive deps) reference
  // process.env.NODE_ENV directly, which doesn't exist in the browser —
  // Vite only replaces import.meta.env by default, not process.env.
  define: {
    "process.env.NODE_ENV": JSON.stringify(mode),
  },
  server: {
    port: 5173,
    // Proxied server-side (on this machine) rather than the browser calling
    // the backend's own port directly -- that assumption breaks under
    // anything that forwards ports independently (a LAN IP with a different
    // firewall story per port, an SSH -L tunnel, VSCode's automatic port
    // forwarding remapping 8000 to 8001 when 8000 is already taken
    // locally...). One forwarded port, 5173, is all any access path needs.
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
}));
