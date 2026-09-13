import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the backend so the session cookie is first-party
// (same origin) exactly as nginx does in docker - no CORS configuration needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.NEXORA_DEV_API_URL ?? "http://localhost:8000", changeOrigin: false },
      "/health": { target: process.env.NEXORA_DEV_API_URL ?? "http://localhost:8000" },
    },
  },
});
