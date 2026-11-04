import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // The Host header stays as the browser sent it, so the server sees one origin, as it does when deployed.
    proxy: { "/api": { target: process.env.API_PROXY ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
});
