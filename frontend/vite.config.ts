import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base URL comes from VITE_API_BASE (see .env.example). In dev the
// /api and /health paths are proxied to the local backend so no URL is
// hard-coded in the frontend.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
      "/health": process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
