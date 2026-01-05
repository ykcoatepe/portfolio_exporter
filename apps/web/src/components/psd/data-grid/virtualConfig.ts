/**
 * PSD Data Grid Virtualization Config
 *
 * Default configurations for virtual scrolling.
 */

import type { VirtualConfig } from "./types";

/**
 * Default virtualization settings
 */
export const DEFAULT_VIRTUAL_CONFIG: VirtualConfig = {
    estimatedRowHeight: 44, // 44px for standard row height
    overscan: 5, // Render 5 extra rows above/below viewport
    enabled: true,
};

/**
 * Compact row virtualization config (denser tables)
 */
export const COMPACT_VIRTUAL_CONFIG: VirtualConfig = {
    estimatedRowHeight: 36,
    overscan: 8,
    enabled: true,
};

/**
 * Large row virtualization config (expanded content)
 */
export const LARGE_VIRTUAL_CONFIG: VirtualConfig = {
    estimatedRowHeight: 64,
    overscan: 3,
    enabled: true,
};

/**
 * Merge partial config with defaults
 */
export function mergeVirtualConfig(
    partial?: Partial<VirtualConfig>,
): VirtualConfig {
    return {
        ...DEFAULT_VIRTUAL_CONFIG,
        ...partial,
    };
}

/**
 * Determine if virtualization should be used based on row count
 */
export function shouldVirtualize(
    rowCount: number,
    config: VirtualConfig,
    threshold: number = 50,
): boolean {
    if (!config.enabled) return false;
    return rowCount > threshold;
}

export default {
    DEFAULT_VIRTUAL_CONFIG,
    COMPACT_VIRTUAL_CONFIG,
    LARGE_VIRTUAL_CONFIG,
    mergeVirtualConfig,
    shouldVirtualize,
};
