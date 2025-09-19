/// <reference types="vitest" />
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    reporters: "default",
    globals: true,
    css: true,
  },
});
