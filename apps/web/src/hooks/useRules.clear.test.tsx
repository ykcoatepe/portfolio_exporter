import { act, render, waitFor } from "@testing-library/react";
import {
  QueryClientProvider,
  type QueryClient,
} from "@tanstack/react-query";
import { describe, expect, test, afterEach, vi } from "vitest";
import { useEffect } from "react";

import { useFundamentals, type UseFundamentalsResult } from "./useRules";
import { server } from "../mocks/server";
import { createTestQueryClient } from "../test/queryClient";

let activeClient: QueryClient | null = null;

afterEach(() => {
  activeClient?.clear();
  activeClient = null;
  server.resetHandlers();
});

function FundamentalsHarness({
  symbols,
  onUpdate,
}: {
  symbols: string[];
  onUpdate: (value: UseFundamentalsResult) => void;
}): null {
  const result = useFundamentals(symbols);
  useEffect(() => {
    onUpdate(result);
  }, [result, onUpdate]);
  return null;
}

describe("useFundamentals", () => {
  test("clears fundamentals when symbol list becomes empty", async () => {
    const handleUpdate = vi.fn((value: UseFundamentalsResult) => value);
    const client = createTestQueryClient();
    activeClient = client;

    const { rerender } = render(
      <QueryClientProvider client={client}>
        <FundamentalsHarness symbols={["AAPL"]} onUpdate={handleUpdate} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const latest = handleUpdate.mock.calls.at(-1)?.[0];
      expect(latest).toBeDefined();
      expect(latest?.data).toHaveLength(1);
      expect(latest?.allFundamentals).not.toBeNull();
    });

    handleUpdate.mockClear();

    act(() => {
      rerender(
        <QueryClientProvider client={client}>
          <FundamentalsHarness symbols={[]} onUpdate={handleUpdate} />
        </QueryClientProvider>,
      );
    });

    await waitFor(() => {
      const latest = handleUpdate.mock.calls.at(-1)?.[0];
      expect(latest).toBeDefined();
      expect(latest?.data).toEqual([]);
      expect(latest?.allFundamentals).toBeNull();
    });
  });
});
