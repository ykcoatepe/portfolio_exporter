import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchMsbSignalsHelp, MSB_HELP_QUERY_KEY } from "../lib/msb";
import type { MsbSignalsHelp } from "../lib/types";

export interface UseMsbSignalsHelpOptions {
  baseUrl?: string;
}

export function useMsbSignalsHelp(
  options: UseMsbSignalsHelpOptions = {},
): UseQueryResult<MsbSignalsHelp, Error> {
  const { baseUrl } = options;
  return useQuery<MsbSignalsHelp, Error>({
    queryKey: MSB_HELP_QUERY_KEY,
    queryFn: () => fetchMsbSignalsHelp(baseUrl),
    retry: false,
  });
}
