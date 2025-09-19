import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import type { components } from "../lib/api";
import type { RuleBreachSummary, RuleCounters, RuleSeverity } from "./useRules";

const RULE_CATALOG_QUERY_KEY = ["rules", "catalog"] as const;

type RawCatalogResponse = components["schemas"]["RulesCatalogResponseModel"];
type RawValidationResponse = components["schemas"]["RulesCatalogValidationResponseModel"];
type RawPublishResponse = components["schemas"]["RulesCatalogPublishResponseModel"];

type RawDiff = components["schemas"]["CatalogDiffModel"] | undefined;

type RawCounters = RawValidationResponse["counters"];
type RawTopEntry = RawValidationResponse["top"] extends Array<infer Item> ? Item : never;

type RawRuleRecord = RawCatalogResponse["rules"] extends Array<infer Item> ? Item : never;

const resolveOrigin = (baseUrl = ""): string => {
  if (baseUrl) {
    return baseUrl.replace(/\/+$/, "");
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "http://localhost";
};

const coerceInteger = (value: unknown, fallback = 0): number => {
  const next = Number(value);
  if (Number.isFinite(next)) {
    return Math.trunc(next);
  }
  return fallback;
};

const coerceString = (value: unknown, fallback = ""): string =>
  typeof value === "string" && value.length > 0 ? value : fallback;

const coerceNullableString = (value: unknown): string | null => {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  return null;
};

const sanitizeSeverity = (value: unknown): RuleSeverity => {
  if (value === "critical" || value === "warning" || value === "info") {
    return value;
  }
  return "info";
};

const coerceNumber = (value: unknown): number | null => {
  const next = Number(value);
  if (Number.isFinite(next)) {
    return next;
  }
  return null;
};

const sanitizeRuleRecord = (value: unknown): Record<string, unknown> | null => {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return null;
};

const sanitizeCounters = (value: RawCounters | undefined): RuleCounters => {
  if (!value || typeof value !== "object") {
    return { total: 0, critical: 0, warning: 0, info: 0 };
  }
  const critical = coerceInteger((value as Record<string, unknown>).critical, 0);
  const warning = coerceInteger((value as Record<string, unknown>).warning, 0);
  const info = coerceInteger((value as Record<string, unknown>).info, 0);
  const totalRaw = coerceInteger((value as Record<string, unknown>).total, critical + warning + info);
  return {
    total: totalRaw,
    critical,
    warning,
    info,
  };
};

const sanitizeTopEntry = (value: RawTopEntry): RuleBreachSummary | null => {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  const id = coerceString(record.id, "");
  const rule = coerceString(record.rule, "");
  const subject = coerceString(record.subject, "");
  const occurredAt = coerceString(record.occurred_at, "");
  if (!id || !rule || !subject || !occurredAt) {
    return null;
  }
  return {
    id,
    rule,
    subject,
    severity: sanitizeSeverity(record.severity),
    symbol: coerceNullableString(record.symbol),
    occurred_at: occurredAt,
    description: coerceNullableString(record.description),
  };
};

const sanitizeDiff = (diff: RawDiff): CatalogDiff => {
  if (!diff || typeof diff !== "object") {
    return { added: [], removed: [], changed: [] };
  }
  const record = diff as Record<string, unknown>;
  const added = Array.isArray(record.added)
    ? record.added
        .map(sanitizeRuleRecord)
        .filter((item): item is Record<string, unknown> => item !== null)
    : [];
  const removed = Array.isArray(record.removed)
    ? record.removed
        .map(sanitizeRuleRecord)
        .filter((item): item is Record<string, unknown> => item !== null)
    : [];
  const changed = Array.isArray(record.changed)
    ? record.changed
        .map(sanitizeRuleRecord)
        .filter((item): item is Record<string, unknown> => item !== null)
    : [];
  return { added, removed, changed };
};

export interface RuleCatalogInfo {
  version: number;
  updatedAt: string | null;
  updatedBy: string | null;
  rules: Record<string, unknown>[];
  rulesCount: number;
}

export interface CatalogDiff {
  added: Record<string, unknown>[];
  removed: Record<string, unknown>[];
  changed: Record<string, unknown>[];
}

export interface RuleCatalogValidationResult {
  ok: boolean;
  counters: RuleCounters;
  top: RuleBreachSummary[];
  errors: string[];
  diff: CatalogDiff | null;
}

export interface RuleCatalogPublishResult {
  version: number;
  updatedAt: string;
  updatedBy: string | null;
}

const normalizeCatalogResponse = (raw: RawCatalogResponse): RuleCatalogInfo => {
  const version = coerceInteger(raw?.version ?? 0, 0);
  const updatedAt = coerceString(raw?.updated_at, "");
  const updatedBy = coerceNullableString(raw?.updated_by);
  const rulesPayload = Array.isArray(raw?.rules) ? raw.rules : [];
  const rules = rulesPayload
    .map(sanitizeRuleRecord)
    .filter((item): item is Record<string, unknown> => item !== null);
  return {
    version,
    updatedAt: updatedAt || null,
    updatedBy,
    rules,
    rulesCount: rules.length,
  };
};

const normalizeValidationResponse = (
  raw: RawValidationResponse,
  diff?: RawDiff,
): RuleCatalogValidationResult => {
  const topEntries = Array.isArray(raw?.top) ? raw.top : [];
  const top = topEntries
    .map(sanitizeTopEntry)
    .filter((item): item is RuleBreachSummary => item !== null);
  const errors = Array.isArray(raw?.errors)
    ? raw.errors.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
  return {
    ok: Boolean(raw?.ok),
    counters: sanitizeCounters(raw?.counters),
    top,
    errors,
    diff: diff ? sanitizeDiff(diff) : null,
  };
};

const normalizePublishResponse = (raw: RawPublishResponse): RuleCatalogPublishResult => ({
  version: coerceInteger(raw?.version ?? 0, 0),
  updatedAt: coerceString(raw?.updated_at, new Date().toISOString()),
  updatedBy: coerceNullableString(raw?.updated_by),
});

async function fetchRuleCatalog(baseUrl = ""): Promise<RuleCatalogInfo> {
  const origin = resolveOrigin(baseUrl);
  const response = await fetch(`${origin}/rules/catalog`, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load rules catalog (${response.status})`);
  }
  const payload = (await response.json()) as RawCatalogResponse;
  return normalizeCatalogResponse(payload);
}

interface ValidateVariables {
  catalogText: string;
  preview?: boolean;
}

async function postValidateRules(
  variables: ValidateVariables,
  baseUrl = "",
): Promise<RuleCatalogValidationResult> {
  const origin = resolveOrigin(baseUrl);
  const endpoint = variables.preview ? "/rules/preview" : "/rules/validate";
  const response = await fetch(`${origin}${endpoint}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({ catalog_text: variables.catalogText }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new Error(`Catalog validation failed (${detail})`);
  }
  const payload = (await response.json()) as RawValidationResponse & {
    diff?: RawDiff;
  };
  return normalizeValidationResponse(payload, payload?.diff);
}

interface PublishVariables {
  catalogText: string;
  author?: string | null;
}

async function postPublishRules(
  variables: PublishVariables,
  baseUrl = "",
): Promise<RuleCatalogPublishResult> {
  const origin = resolveOrigin(baseUrl);
  const response = await fetch(`${origin}/rules/publish`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      catalog_text: variables.catalogText,
      author: variables.author ?? null,
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new Error(`Catalog publish failed (${detail})`);
  }
  const payload = (await response.json()) as RawPublishResponse;
  return normalizePublishResponse(payload);
}

async function postReloadRules(baseUrl = ""): Promise<RuleCatalogInfo> {
  const origin = resolveOrigin(baseUrl);
  const response = await fetch(`${origin}/rules/reload`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Catalog reload failed (${response.status})`);
  }
  const payload = (await response.json()) as RawCatalogResponse;
  return normalizeCatalogResponse(payload);
}

export function useRuleCatalog(): UseQueryResult<RuleCatalogInfo, Error> {
  return useQuery<RuleCatalogInfo, Error>({
    queryKey: RULE_CATALOG_QUERY_KEY,
    queryFn: () => fetchRuleCatalog(),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
}

export function useReloadRules(): UseMutationResult<RuleCatalogInfo, Error, void> {
  const queryClient = useQueryClient();
  return useMutation<RuleCatalogInfo, Error, void>({
    mutationFn: () => postReloadRules(),
    onSuccess: (data) => {
      queryClient.setQueryData(RULE_CATALOG_QUERY_KEY, data);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: RULE_CATALOG_QUERY_KEY });
    },
  });
}

export function useValidateRules(): UseMutationResult<RuleCatalogValidationResult, Error, ValidateVariables> {
  return useMutation<RuleCatalogValidationResult, Error, ValidateVariables>({
    mutationFn: (variables) => postValidateRules(variables),
  });
}

export function usePreviewRules(): UseMutationResult<RuleCatalogValidationResult, Error, ValidateVariables> {
  return useMutation<RuleCatalogValidationResult, Error, ValidateVariables>({
    mutationFn: (variables) => postValidateRules({ ...variables, preview: true }),
  });
}

export function usePublishRules(): UseMutationResult<RuleCatalogPublishResult, Error, PublishVariables> {
  const queryClient = useQueryClient();
  return useMutation<RuleCatalogPublishResult, Error, PublishVariables>({
    mutationFn: (variables) => postPublishRules(variables),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: RULE_CATALOG_QUERY_KEY });
    },
  });
}

