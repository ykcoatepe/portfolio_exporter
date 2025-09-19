import { defineWorkspace } from "vitest/config";

export default defineWorkspace([
  {
    extends: "./vitest.config.ts",
    test: {
      name: "unit",
      environment: "jsdom",
      include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
      setupFiles: ["src/test/setup.ts"],
    },
  },
  {
    extends: "./vitest.config.ts",
    test: {
      name: "contracts",
      environment: "node",
      include: ["tests/contracts/**/*.test.ts"],
      setupFiles: [],
    },
  },
]);
