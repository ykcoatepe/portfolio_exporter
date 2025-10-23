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
  test: {
    globals: true,
    css: true,
  },
});
