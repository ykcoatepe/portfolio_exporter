import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchMsbStatus, MSB_STATUS_QUERY_KEY } from "../lib/msb";
import type { MsbStatus } from "../lib/types";

export interface UseMsbStatusOptions {
  baseUrl?: string;
}

export function useMsbStatus(
  options: UseMsbStatusOptions = {},
): UseQueryResult<MsbStatus, Error> {
  const { baseUrl } = options;
  return useQuery<MsbStatus, Error>({
    queryKey: MSB_STATUS_QUERY_KEY,
    queryFn: () => fetchMsbStatus(baseUrl),
    retry: false,
  });
}
