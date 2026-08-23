import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { "/auth": "http://127.0.0.1:8090", "/tasks": "http://127.0.0.1:8090", "/ingest": "http://127.0.0.1:8090", "/corpus": "http://127.0.0.1:8090", "/languages": "http://127.0.0.1:8090", "/health": "http://127.0.0.1:8090", "/accounts": "http://127.0.0.1:8090", "/coverage": "http://127.0.0.1:8090", "/assignments": "http://127.0.0.1:8090" } },
});


