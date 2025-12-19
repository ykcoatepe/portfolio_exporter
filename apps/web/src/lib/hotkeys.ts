/**
 * PSD Scoped Hotkeys Registry
 *
 * Design:
 * - Hotkeys are scoped to non-input contexts (won't fire when typing in inputs)
 * - Conflict list: Cmd+K (command palette), / (quick search), ? (help)
 * - Each hotkey has a unique ID, key combo, description, and handler
 */

export interface Hotkey {
    id: string;
    /** Key combo (e.g., "cmd+k", "shift+?", "/") */
    keys: string;
    /** Human-readable description for help modal */
    description: string;
    /** Category for grouping in help modal */
    category: "navigation" | "actions" | "view" | "system";
    /** Handler function */
    handler: () => void;
}

// Registry of active hotkeys
const registry = new Map<string, Hotkey>();

// Input elements that should block hotkeys
const INPUT_SELECTORS = ["INPUT", "TEXTAREA", "SELECT"];

/**
 * Check if the current focus is in an input context
 */
function isInputFocused(): boolean {
    const active = document.activeElement;
    if (!active) return false;

    if (INPUT_SELECTORS.includes(active.tagName)) return true;
    if ((active as HTMLElement).isContentEditable) return true;

    return false;
}

/**
 * Parse a key combo string into components
 * e.g., "cmd+k" -> { meta: true, key: "k" }
 */
function parseKeyCombo(keys: string): {
    meta: boolean;
    ctrl: boolean;
    shift: boolean;
    alt: boolean;
    key: string;
} {
    const parts = keys.toLowerCase().split("+");
    const key = parts[parts.length - 1];

    return {
        meta: parts.includes("cmd") || parts.includes("meta"),
        ctrl: parts.includes("ctrl"),
        shift: parts.includes("shift"),
        alt: parts.includes("alt") || parts.includes("option"),
        key,
    };
}

/**
 * Check if a keyboard event matches a hotkey
 */
function matchesHotkey(event: KeyboardEvent, hotkey: Hotkey): boolean {
    const combo = parseKeyCombo(hotkey.keys);
    const eventKey = event.key.toLowerCase();

    // Special handling for "?" which requires shift
    if (combo.key === "?") {
        return (
            event.shiftKey &&
            (eventKey === "?" || eventKey === "/") &&
            combo.meta === event.metaKey &&
            combo.ctrl === event.ctrlKey &&
            combo.alt === event.altKey
        );
    }

    return (
        eventKey === combo.key &&
        combo.meta === event.metaKey &&
        combo.ctrl === event.ctrlKey &&
        combo.shift === event.shiftKey &&
        combo.alt === event.altKey
    );
}

/**
 * Register a hotkey
 */
export function registerHotkey(hotkey: Hotkey): () => void {
    registry.set(hotkey.id, hotkey);

    // Return unregister function
    return () => {
        registry.delete(hotkey.id);
    };
}

/**
 * Unregister a hotkey by ID
 */
export function unregisterHotkey(id: string): void {
    registry.delete(id);
}

/**
 * Get all registered hotkeys (for help modal)
 */
export function getRegisteredHotkeys(): Hotkey[] {
    return Array.from(registry.values());
}

/**
 * Get hotkeys grouped by category
 */
export function getHotkeysByCategory(): Record<Hotkey["category"], Hotkey[]> {
    const result: Record<Hotkey["category"], Hotkey[]> = {
        navigation: [],
        actions: [],
        view: [],
        system: [],
    };

    for (const hotkey of registry.values()) {
        result[hotkey.category].push(hotkey);
    }

    return result;
}

/**
 * Global keyboard event handler
 * Attach this to the window
 */
function handleKeyDown(event: KeyboardEvent): void {
    // Skip if focused on input
    if (isInputFocused()) return;

    for (const hotkey of registry.values()) {
        if (matchesHotkey(event, hotkey)) {
            event.preventDefault();
            event.stopPropagation();
            hotkey.handler();
            return;
        }
    }
}

let isListenerAttached = false;

/**
 * Initialize the hotkey system
 * Call once on app mount
 */
export function initHotkeys(): () => void {
    if (typeof window === "undefined") return () => { };

    if (isListenerAttached) return () => { };

    window.addEventListener("keydown", handleKeyDown);
    isListenerAttached = true;

    // Return cleanup function
    return () => {
        window.removeEventListener("keydown", handleKeyDown);
        isListenerAttached = false;
        registry.clear();
    };
}

/**
 * Format a key combo for display
 * e.g., "cmd+k" -> "⌘K" (on Mac)
 */
export function formatKeyCombo(keys: string): string {
    const isMac =
        typeof navigator !== "undefined" &&
        navigator.platform.toUpperCase().includes("MAC");

    return keys
        .split("+")
        .map((part) => {
            const lower = part.toLowerCase();
            if (lower === "cmd" || lower === "meta") return isMac ? "⌘" : "Ctrl";
            if (lower === "ctrl") return isMac ? "⌃" : "Ctrl";
            if (lower === "shift") return isMac ? "⇧" : "Shift";
            if (lower === "alt" || lower === "option") return isMac ? "⌥" : "Alt";
            if (lower === "enter") return "↵";
            if (lower === "escape" || lower === "esc") return "Esc";
            if (lower === "arrowup") return "↑";
            if (lower === "arrowdown") return "↓";
            if (lower === "arrowleft") return "←";
            if (lower === "arrowright") return "→";
            return part.toUpperCase();
        })
        .join("");
}
