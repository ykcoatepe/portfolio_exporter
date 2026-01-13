import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { DEFAULT_API_BASE_URL, resolveApiBaseUrl } from "./http";

declare global {
  // eslint-disable-next-line no-var
  var window: Window & typeof globalThis;
}

describe("resolveApiBaseUrl", () => {
  const originalWindow = globalThis.window;

  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  afterEach(() => {
    if (originalWindow) {
      globalThis.window = originalWindow;
    } else {
      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete (globalThis as Record<string, unknown>).window;
    }
    vi.unstubAllEnvs();
  });

  test("returns provided base URL without trailing slash", () => {
    expect(resolveApiBaseUrl("https://example.com/api/")).toBe("https://example.com/api");
  });

  test("uses window origin and ignores Vite base path", () => {
    vi.stubEnv("BASE_URL", "/psd/");
    globalThis.window = {
      location: { origin: "https://dash.example.com" },
    } as unknown as Window & typeof globalThis;

    expect(resolveApiBaseUrl()).toBe("https://dash.example.com");
  });

  test("falls back to localhost when window is unavailable", () => {
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete (globalThis as Record<string, unknown>).window;
    expect(resolveApiBaseUrl()).toBe(DEFAULT_API_BASE_URL);
  });
});
