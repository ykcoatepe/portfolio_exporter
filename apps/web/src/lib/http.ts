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
    const origin = sanitizeBaseUrl(window.location.origin);
    const basePath = resolveBasePath();

    try {
      const absolute = new URL(basePath, `${origin}/`).href;
      return sanitizeBaseUrl(absolute);
    } catch (error) {
      const normalizedPath = basePath.startsWith("/") ? basePath : `/${basePath}`;
      return sanitizeBaseUrl(`${origin}${normalizedPath}`);
    }
  }

  return DEFAULT_API_BASE_URL;
};
