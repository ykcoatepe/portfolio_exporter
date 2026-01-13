import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchPowerlawSignalsHelp, POWERLAW_HELP_QUERY_KEY } from "../lib/powerlaw";
import type { PowerlawSignalsHelp } from "../lib/types";

export interface UsePowerlawSignalsHelpOptions {
  baseUrl?: string;
  enabled?: boolean;
}

export function usePowerlawSignalsHelp(
  options: UsePowerlawSignalsHelpOptions = {},
): UseQueryResult<PowerlawSignalsHelp, Error> {
  const { baseUrl, enabled = true } = options;
  return useQuery<PowerlawSignalsHelp, Error>({
    queryKey: POWERLAW_HELP_QUERY_KEY,
    queryFn: () => fetchPowerlawSignalsHelp(baseUrl),
    retry: false,
    enabled,
  });
}
