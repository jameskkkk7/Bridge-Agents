import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// The API port is configurable because another local service may already own
// 8000; `npm run dev` keeps working with the default when it is free.
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";
const wsTarget = process.env.VITE_WS_TARGET ?? apiTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/health": { target: apiTarget, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true },
    },
  },
});
