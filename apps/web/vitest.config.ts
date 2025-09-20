/// <reference types="vitest" />
import path from "node:path";
import { defineConfig, defineProject } from "vitest/config";

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
    projects: [
      defineProject({
        test: {
          name: "unit",
          environment: "jsdom",
          include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
          setupFiles: ["src/test/setup.ts"],
        },
      }),
      defineProject({
        test: {
          name: "contracts",
          environment: "node",
          include: ["tests/contracts/**/*.test.ts"],
        },
      }),
    ],
  },
});
