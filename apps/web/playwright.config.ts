import { defineConfig } from "@playwright/test";

const PORT = process.env.PLAYWRIGHT_WEB_PORT ? Number(process.env.PLAYWRIGHT_WEB_PORT) : 4173;
const HOST = "127.0.0.1";
const BASE_URL = `http://${HOST}:${PORT}`;

export default defineConfig({
  testDir: "tests",
  testMatch: "**/*.e2e.spec.ts",
  timeout: 60_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  testMatch: ["**/*.e2e.spec.ts"],
  webServer: {
    command: `bun run dev -- --host ${HOST} --port ${PORT}`,
    url: BASE_URL,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
