import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { "/auth": "http://127.0.0.1:8080", "/tasks": "http://127.0.0.1:8080", "/ingest": "http://127.0.0.1:8080", "/corpus": "http://127.0.0.1:8080", "/languages": "http://127.0.0.1:8080", "/health": "http://127.0.0.1:8080" } },
});
