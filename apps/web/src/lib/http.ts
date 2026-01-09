export const DEFAULT_API_BASE_URL = "http://localhost";

const sanitizeBaseUrl = (value: string): string => value.replace(/\/+$/, "");

const resolveBasePath = (): string => {
  const base =
    (typeof import.meta !== "undefined" && typeof import.meta.env?.BASE_URL === "string"
      ? import.meta.env.BASE_URL
      : "/") || "/";
  return base.trim() || "/";
};

export const resolveApiBaseUrl = (baseUrl?: string): string => {
  if (typeof baseUrl === "string" && baseUrl.trim().length > 0) {
    return sanitizeBaseUrl(baseUrl.trim());
  }

  if (typeof window !== "undefined" && typeof window.location?.origin === "string") {
    return sanitizeBaseUrl(window.location.origin);
  }

  return DEFAULT_API_BASE_URL;
};
