import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  resolve: {
    alias: {
      "react-router-dom": path.resolve(__dirname, "src/vendor/react-router-dom.tsx"),
    },
  },
  plugins: [react()],
  server: {
    proxy: {
      "/state": "http://127.0.0.1:51127",
      "/stats": "http://127.0.0.1:51127",
      "/positions": "http://127.0.0.1:51127",
      "/msb": "http://127.0.0.1:51127",
      "/rules": "http://127.0.0.1:51127",
      "/sse": "http://127.0.0.1:51127",
      "/session": "http://127.0.0.1:51127",
    },
  },
  test: {
    globals: true,
    css: true,
  },
});
