import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

declare global {
  // React Testing Library v15 respects this flag when act(...) is used manually.
  // eslint-disable-next-line no-var, vars-on-top
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
if (typeof globalThis.window !== "undefined") {
  globalThis.window.IS_REACT_ACT_ENVIRONMENT = true;
}

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

if (!globalThis.Element.prototype.scrollIntoView) {
  globalThis.Element.prototype.scrollIntoView = () => { };
}

if (!("ResizeObserver" in globalThis)) {
  class ResizeObserverMock {
    private callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
    }

    observe(target: Element): void {
      const rect = (target as HTMLElement).getBoundingClientRect();
      this.callback(
        [
          {
            target,
            contentRect: rect,
          } as ResizeObserverEntry,
        ],
        this,
      );
    }
    unobserve(): void { }
    disconnect(): void { }
  }
  globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof globalThis.ResizeObserver;
}

const defaultRect = {
  width: 1024,
  height: 768,
  top: 0,
  left: 0,
  right: 1024,
  bottom: 768,
  x: 0,
  y: 0,
  toJSON() {
    return this;
  },
};

const applyLayoutOverrides = (prototype: typeof globalThis.HTMLElement.prototype) => {
  const originalGetBoundingClientRect = prototype.getBoundingClientRect;
  prototype.getBoundingClientRect = function getBoundingClientRect() {
    if (originalGetBoundingClientRect) {
      const rect = originalGetBoundingClientRect.call(this);
      if (rect.width || rect.height) {
        return rect;
      }
    }
    return defaultRect as DOMRect;
  };

  for (const key of ["clientWidth", "clientHeight", "offsetWidth", "offsetHeight"] as const) {
    Object.defineProperty(prototype, key, {
      configurable: true,
      get() {
        return key.includes("Width") ? defaultRect.width : defaultRect.height;
      },
    });
  }
};

if (globalThis.HTMLElement?.prototype) {
  applyLayoutOverrides(globalThis.HTMLElement.prototype);
}
if (globalThis.SVGElement?.prototype) {
  applyLayoutOverrides(
    globalThis.SVGElement.prototype as unknown as typeof globalThis.HTMLElement.prototype,
  );
}

if (
  !globalThis.localStorage ||
  typeof globalThis.localStorage.getItem !== "function"
) {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
  };
  globalThis.localStorage = storage;
}

let server: typeof import("../mocks/server").server | undefined;

if (
  !globalThis.sessionStorage ||
  typeof globalThis.sessionStorage.getItem !== "function"
) {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
  };
  globalThis.sessionStorage = storage;
}

const rafSpy = vi
  .spyOn(globalThis, "requestAnimationFrame")
  .mockImplementation((callback: FrameRequestCallback): number => {
    return setTimeout(() => callback(Date.now()), 0) as unknown as number;
  });

const cafSpy = vi
  .spyOn(globalThis, "cancelAnimationFrame")
  .mockImplementation((handle: number) => {
    clearTimeout(handle);
  });

beforeAll(async () => {
  const mod = await import("../mocks/server");
  server = mod.server;
  server.listen({ onUnhandledRequest: "bypass" });
});
afterEach(() => {
  cleanup();
  server?.resetHandlers();
});
afterAll(() => {
  rafSpy.mockRestore();
  cafSpy.mockRestore();
  server?.close();
});
