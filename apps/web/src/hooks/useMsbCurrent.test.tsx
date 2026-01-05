import { render, waitFor } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { beforeAll, afterAll, afterEach, describe, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { useEffect } from "react";

import { useMsbCurrent } from "./useMsbCurrent";
import type { MsbReading } from "../lib/types";
import { buildMsbHistory, buildMsbReading } from "../mocks/handlers";
import { server } from "../mocks/server";
import { createTestQueryClient } from "../test/queryClient";

class EventSourceMock {
  static instances: EventSourceMock[] = [];

  readonly url: string;
  readonly withCredentials: boolean;
  private listeners: Map<string, Set<(event: MessageEvent<string>) => void>> = new Map();
  readyState = 1;

  constructor(url: string, init?: EventSourceInit) {
    this.url = url;
    this.withCredentials = Boolean(init?.withCredentials);
    EventSourceMock.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string, payload: unknown): void {
    const listeners = this.listeners.get(type);
    if (!listeners || listeners.size === 0) {
      return;
    }
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
    listeners.forEach((callback) => callback(event));
  }

  close(): void {
    this.readyState = 2;
    this.listeners.clear();
  }
}

type UseMsbResult = ReturnType<typeof useMsbCurrent>;

let originalEventSource: typeof EventSource | undefined;
let activeClient: QueryClient | null = null;

beforeAll(() => {
  originalEventSource = globalThis.EventSource;
  globalThis.EventSource = EventSourceMock as unknown as typeof EventSource;
});

afterAll(() => {
  if (originalEventSource) {
    globalThis.EventSource = originalEventSource;
  } else {
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete (globalThis as Record<string, unknown>).EventSource;
  }
});

afterEach(() => {
  activeClient?.clear();
  activeClient = null;
  EventSourceMock.instances = [];
  server.resetHandlers();
  vi.clearAllMocks();
});

function HookHarness({ onValue }: { onValue: (value: UseMsbResult) => void }): null {
  const result = useMsbCurrent();
  useEffect(() => {
    onValue(result);
  }, [result, onValue]);
  return null;
}

describe("useMsbCurrent", () => {
  test("updates the query cache when an msb.update SSE arrives", async () => {
    const initial = buildMsbReading({ msb: 24, color: "yellow", triggers: [] });
    const updated: MsbReading = { ...initial, msb: 36, color: "orange", date: "2024-02-03" };
    server.use(
      http.get("*/msb/current", () => HttpResponse.json(initial)),
      http.get("*/msb/history", () => HttpResponse.json(buildMsbHistory(7))),
    );

    const onValue = vi.fn<(value: UseMsbResult) => void>();
    const client = createTestQueryClient();
    activeClient = client;

    render(
      <QueryClientProvider client={client}>
        <HookHarness onValue={onValue} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const current = client.getQueryData<MsbReading>(["msb.current"]);
      expect(current?.msb).toBe(initial.msb);
    });

    const source = EventSourceMock.instances.at(0);
    expect(source).toBeDefined();
    expect(source?.withCredentials).toBe(true);

    source?.emit("msb.update", updated);

    await waitFor(() => {
      const next = client.getQueryData<MsbReading>(["msb.current"]);
      expect(next?.msb).toBe(updated.msb);
      expect(onValue.mock.calls.at(-1)?.[0].data?.msb).toBe(updated.msb);
    });
  });
});
