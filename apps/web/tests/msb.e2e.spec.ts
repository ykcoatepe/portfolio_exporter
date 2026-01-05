import { expect, test } from "@playwright/test";

declare global {
  interface Window {
    __msbSseMock?: {
      instances: unknown[];
      emit: (payload: unknown) => void;
    };
  }
}

const injectSseMock = () => {
  const globalAny = window as typeof window;

  class TestEventSource {
    static instances: TestEventSource[] = [];

    readonly url: string;
    readonly withCredentials: boolean;
    private listeners = new Map<string, Set<(event: MessageEvent<string>) => void>>();

    constructor(url: string, init?: EventSourceInit) {
      this.url = url;
      this.withCredentials = Boolean(init?.withCredentials);
      TestEventSource.instances.push(this);
      if (!globalAny.__msbSseMock) {
        globalAny.__msbSseMock = {
          instances: TestEventSource.instances,
          emit(payload: unknown) {
            TestEventSource.instances.forEach((instance) =>
              instance.dispatch("msb.update", payload),
            );
          },
        };
      }
    }

    addEventListener(type: string, callback: (event: MessageEvent<string>) => void): void {
      if (!this.listeners.has(type)) {
        this.listeners.set(type, new Set());
      }
      this.listeners.get(type)?.add(callback);
    }

    removeEventListener(type: string, callback: (event: MessageEvent<string>) => void): void {
      this.listeners.get(type)?.delete(callback);
    }

    dispatch(type: string, payload: unknown): void {
      const listeners = this.listeners.get(type);
      if (!listeners) {
        return;
      }
      const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
      listeners.forEach((listener) => listener(event));
    }

    close(): void {
      this.listeners.clear();
    }
  }

  // @ts-expect-error override native EventSource for test environment
  window.EventSource = TestEventSource;
};

test("MSB gauge reflects SSE updates", async ({ page }) => {
  await page.addInitScript(injectSseMock);
  await page.goto("/psd");

  const gauge = page.getByText(/Stress:/).first();
  const initialText = await gauge.textContent();
  expect(initialText).toBeTruthy();

  await page.evaluate(() => {
    const payload = {
      date: "2024-02-05",
      hy: 4.25,
      vx1: 18.4,
      vx2: 19.7,
      z_hy: 0.71,
      term_ratio: 1.04,
      cal_spread_pct: 0.047,
      cal_spread_abs: 0.82,
      saturated: false,
      hy_score: 26,
      vix_score: 28,
      msb: 42,
      color: "red",
      triggers: ["RULE_C_MSB_60x3D"],
      winsor_clipped_n: 0,
      cooldown_until: null,
    };
    window.__msbSseMock?.emit(payload);
  });

  await expect(page.getByText("Stress: 42 — Red")).toBeVisible({ timeout: 3_000 });
  expect(initialText).not.toBe("Stress: 42 — Red");
});
