import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { server } from "../mocks/server";

declare global {
  // React Testing Library v15 respects this flag when act(...) is used manually.
  // eslint-disable-next-line no-var, vars-on-top
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = ((callback: FrameRequestCallback): number => {
    return setTimeout(() => callback(Date.now()), 16) as unknown as number;
  }) as typeof globalThis.requestAnimationFrame;
}

if (!globalThis.cancelAnimationFrame) {
  globalThis.cancelAnimationFrame = ((handle: number): void => {
    clearTimeout(handle);
  }) as typeof globalThis.cancelAnimationFrame;
}

const rafSpy = vi
  .spyOn(globalThis, "requestAnimationFrame")
  .mockImplementation((callback: FrameRequestCallback): number => {
    callback(Date.now());
    return 0;
  });

const cafSpy = vi
  .spyOn(globalThis, "cancelAnimationFrame")
  .mockImplementation(() => {
    /* no-op */
  });

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => {
  rafSpy.mockRestore();
  cafSpy.mockRestore();
  server.close();
});
