import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: {
      usePolling: true,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
    // HMR connects back through the Caddy TLS proxy rather than direct to the Vite dev port.
    hmr: { protocol: "wss", host: "0.0.0.0", clientPort: 443 },
  },
});
