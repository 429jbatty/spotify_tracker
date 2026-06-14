import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path"
import { fileURLToPath } from "url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const basePath = process.env.VITE_BASE_PATH || "/"
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000"

export default defineConfig({
  plugins: [react()],
  base: basePath,
  server: {
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/media": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
