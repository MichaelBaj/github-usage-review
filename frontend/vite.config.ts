import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/copilot/",
  plugins: [react()],
  server: {
    port: 5173,
    watch: {
      usePolling: true,
    },
    proxy: {
      "/copilot/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/copilot\/api/, "/api"),
      },
    },
    // HMR connects back through the Caddy TLS proxy rather than direct to the Vite dev port.
    hmr: { protocol: "wss", host: "0.0.0.0", clientPort: 443 },
  },
});
