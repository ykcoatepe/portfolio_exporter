import { resolveApiBaseUrl } from "./http";
import type { PowerlawHelpSection, PowerlawHelpTerm, PowerlawSignalsHelp } from "./types";

const toStringField = (value: unknown, field: string): string => {
  if (typeof value !== "string") {
    throw new Error(`Invalid Powerlaw help field: ${field}`);
  }
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error(`Invalid Powerlaw help field: ${field}`);
  }
  return trimmed;
};

const toOptionalString = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const toStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item): item is string => item.length > 0);
};

export const POWERLAW_HELP_QUERY_KEY = ["powerlaw.help"] as const;

const parsePowerlawHelpSection = (
  payload: unknown,
  index: number,
): PowerlawHelpSection => {
  if (!payload || typeof payload !== "object") {
    throw new Error(`Invalid Powerlaw help section ${index + 1}`);
  }
  const record = payload as Record<string, unknown>;
  const title = toStringField(record.title, "title");
  const bullets = toStringArray(record.bullets);
  if (!bullets.length) {
    throw new Error(`Invalid Powerlaw help section bullets ${index + 1}`);
  }
  return { title, bullets };
};

const parsePowerlawHelpTerm = (payload: unknown): PowerlawHelpTerm | null => {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  try {
    const key = toStringField(record.key, "key");
    const title = toStringField(record.title, "title");
    const body = toOptionalString(record.body);
    const bullets = toStringArray(record.bullets);
    return {
      key,
      title,
      body: body ?? null,
      bullets: bullets.length > 0 ? bullets : null,
    };
  } catch {
    return null;
  }
};

export const parsePowerlawSignalsHelp = (payload: unknown): PowerlawSignalsHelp => {
  if (!payload || typeof payload !== "object") {
    throw new Error("Invalid Powerlaw help payload");
  }
  const record = payload as Record<string, unknown>;
  const title = toStringField(record.title, "title");
  const subtitle = toOptionalString(record.subtitle);
  const sectionsRaw = Array.isArray(record.sections) ? record.sections : [];
  const sections = sectionsRaw.map((section, index) =>
    parsePowerlawHelpSection(section, index),
  );
  const termsRaw = Array.isArray(record.terms) ? record.terms : [];
  const terms = termsRaw
    .map((term) => parsePowerlawHelpTerm(term))
    .filter((term): term is NonNullable<typeof term> => Boolean(term));
  const footnotes = toStringArray(record.footnotes);
  return {
    title,
    subtitle,
    sections,
    terms: terms.length > 0 ? terms : null,
    footnotes: footnotes.length > 0 ? footnotes : null,
  };
};

export const fetchPowerlawSignalsHelp = async (baseUrl?: string): Promise<PowerlawSignalsHelp> => {
  const origin = resolveApiBaseUrl(baseUrl);
  const response = await fetch(`${origin}/powerlaw/help`, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Powerlaw help request failed with status ${response.status}`);
  }
  const payload = (await response.json()) as unknown;
  return parsePowerlawSignalsHelp(payload);
};
