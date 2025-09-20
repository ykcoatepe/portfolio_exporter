/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vitest/config";

const routerAlias = path.resolve(__dirname, "src/vendor/react-router-dom.tsx");

export default defineConfig({
  resolve: {
    alias: {
      "react-router-dom": routerAlias,
    },
  },
  test: {
    reporters: "default",
    globals: true,
    css: true,
  },
});
