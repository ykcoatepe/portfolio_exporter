/**
 * PSD Theme Configuration
 *
 * Design Rules:
 * 1. Data surfaces use SOLID high-contrast backgrounds.
 * 2. Glassmorphism is for framing/context UI only.
 * 3. Motion respects prefers-reduced-motion and user settings.
 */

// Terminal-first color palette (high contrast)
export const colors = {
  // Background hierarchy (solid, no glass on data)
  bg: {
    base: "hsl(222 47% 11%)", // slate-900
    surface: "hsl(217 33% 17%)", // slate-800
    elevated: "hsl(215 28% 22%)", // slate-700
    data: "hsl(222 47% 11%)", // Pure solid for data tables
  },

  // Text hierarchy
  text: {
    primary: "hsl(210 40% 98%)", // slate-50
    secondary: "hsl(215 20% 65%)", // slate-400
    muted: "hsl(215 16% 47%)", // slate-500
  },

  // Semantic colors
  positive: "hsl(142 76% 36%)", // green-600
  negative: "hsl(0 84% 60%)", // red-500
  warning: "hsl(45 93% 47%)", // amber-500
  info: "hsl(199 89% 48%)", // sky-500

  // Accent (command palette, focus rings)
  accent: {
    primary: "hsl(199 89% 48%)", // sky-500
    hover: "hsl(199 89% 58%)", // sky-400
  },

  // Border
  border: {
    default: "hsl(217 33% 23%)", // slate-700/60 equivalent
    subtle: "hsl(217 33% 17% / 0.6)",
  },
} as const;

// Typography (terminal-friendly)
export const fonts = {
  sans: "'Inter', system-ui, -apple-system, sans-serif",
  mono: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace",
} as const;

// Motion config (gated by preferences)
export const motion = {
  // Standard durations
  fast: "150ms",
  normal: "200ms",
  slow: "300ms",

  // Easing
  ease: "cubic-bezier(0.4, 0, 0.2, 1)",
  easeIn: "cubic-bezier(0.4, 0, 1, 1)",
  easeOut: "cubic-bezier(0, 0, 0.2, 1)",
} as const;

// Spacing scale (compact for terminal density)
export const spacing = {
  xs: "0.25rem", // 4px
  sm: "0.5rem", // 8px
  md: "0.75rem", // 12px
  lg: "1rem", // 16px
  xl: "1.5rem", // 24px
} as const;

// CSS variable names (used in index.css)
export const cssVars = {
  // Motion toggle (set by preferences store)
  motionDuration: "--psd-motion-duration",
  motionEnabled: "--psd-motion-enabled",

  // Translucency toggle
  glassOpacity: "--psd-glass-opacity",
  glassBlur: "--psd-glass-blur",

  // Colors (can be themed)
  bgBase: "--psd-bg-base",
  bgSurface: "--psd-bg-surface",
  bgData: "--psd-bg-data",
  textPrimary: "--psd-text-primary",
  textSecondary: "--psd-text-secondary",
  borderDefault: "--psd-border-default",
} as const;

// Helper to check if reduced motion is preferred
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Helper to apply motion-safe transitions
export function safeTransition(property: string, duration = motion.normal): string {
  return `${property} var(${cssVars.motionDuration}, ${duration}) ${motion.ease}`;
}
