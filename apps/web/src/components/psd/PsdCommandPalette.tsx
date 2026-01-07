import type { ReactNode } from "react";
import { Command } from "cmdk";
import { useEffect, useState } from "react";
import {
    BarChart3,
    Grid3X3,
    HelpCircle,
    LayoutDashboard,
    RefreshCw,
    Settings,
    Sliders,
    Table2,
    X,
} from "lucide-react";

import { formatKeyCombo, registerHotkey } from "../../lib/hotkeys";
import { usePsdPreferences } from "../../state/psdPreferencesStore";

/**
 * PSD Command Palette
 *
 * Keyboard-first navigation for the dashboard.
 * Trigger: Cmd+K (Mac) or Ctrl+K (Windows) - both registered
 *
 * Design:
 * - Glass effect on overlay per plan (framing UI)
 * - Solid background on input/results (data-like)
 * - Grouped commands by category
 */

export interface CommandItem {
    id: string;
    label: string;
    description?: string;
    icon?: ReactNode;
    shortcut?: string;
    category: "navigation" | "actions" | "view" | "system";
    onSelect: () => void;
}

interface PsdCommandPaletteProps {
    /** External control of open state */
    open?: boolean;
    /** Callback when open state changes */
    onOpenChange?: (open: boolean) => void;
    /** Custom commands to add */
    commands?: CommandItem[];
    /** Callback to open settings */
    onOpenSettings?: () => void;
    /** Callback to open help */
    onOpenHelp?: () => void;
}

/**
 * Get scroll behavior respecting reduced motion preference
 */
function getScrollBehavior(): ScrollBehavior {
    if (typeof window === "undefined") return "auto";
    const reducedMotion = document.documentElement.dataset.reducedMotion === "true";
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    return reducedMotion || prefersReduced ? "auto" : "smooth";
}

export function PsdCommandPalette({
    open: controlledOpen,
    onOpenChange,
    commands = [],
    onOpenSettings,
    onOpenHelp,
}: PsdCommandPaletteProps) {
    const [internalOpen, setInternalOpen] = useState(false);
    const [search, setSearch] = useState("");
    const { toggleSidebar } = usePsdPreferences();

    const isOpen = controlledOpen ?? internalOpen;
    const setOpen = onOpenChange ?? setInternalOpen;

    const defaultCommands: CommandItem[] = [
        {
            id: "nav-dashboard",
            label: "Go to Dashboard",
            icon: <LayoutDashboard size={16} />,
            category: "navigation",
            onSelect: () => {
                document.querySelector('[aria-label="Portfolio Sentinel sections"]')?.scrollIntoView({ behavior: getScrollBehavior() });
            },
        },
        {
            id: "nav-stocks",
            label: "Go to Stocks Table",
            icon: <Table2 size={16} />,
            category: "navigation",
            onSelect: () => {
                document.querySelector('[aria-label="Single Stocks"]')?.scrollIntoView({ behavior: getScrollBehavior() });
            },
        },
        {
            id: "nav-options",
            label: "Go to Options",
            icon: <Grid3X3 size={16} />,
            category: "navigation",
            onSelect: () => {
                // Target Options section - try both possible labels
                const optionsSection =
                    document.querySelector('[aria-label="Options — Combos"]') ||
                    document.querySelector('[aria-label="Options"]') ||
                    document.querySelector('[aria-label="Options — Singles"]');
                optionsSection?.scrollIntoView({ behavior: getScrollBehavior() });
            },
        },
        {
            id: "action-refresh",
            label: "Refresh Data",
            icon: <RefreshCw size={16} />,
            category: "actions",
            onSelect: () => {
                // Trigger page refresh for now
                window.location.reload();
            },
        },
        {
            id: "view-toggle-sidebar",
            label: "Toggle Sidebar",
            icon: <Sliders size={16} />,
            shortcut: "cmd+b",
            category: "view",
            onSelect: () => {
                toggleSidebar();
            },
        },
        {
            id: "view-charts",
            label: "Show Charts",
            icon: <BarChart3 size={16} />,
            category: "view",
            onSelect: () => {
                document.querySelector('[aria-label="Market Stress Barometer overview"]')?.scrollIntoView({ behavior: getScrollBehavior() });
            },
        },
        {
            id: "system-settings",
            label: "Open Settings",
            icon: <Settings size={16} />,
            shortcut: "cmd+,",
            category: "system",
            onSelect: () => {
                onOpenSettings?.();
            },
        },
        {
            id: "system-help",
            label: "Keyboard Shortcuts",
            icon: <HelpCircle size={16} />,
            shortcut: "?",
            category: "system",
            onSelect: () => {
                onOpenHelp?.();
            },
        },
    ];

    // Register Cmd+K and Ctrl+K hotkeys for cross-platform support
    useEffect(() => {
        const unregisterCmd = registerHotkey({
            id: "command-palette-cmd",
            keys: "cmd+k",
            description: "Open command palette",
            category: "system",
            handler: () => setOpen(true),
        });

        const unregisterCtrl = registerHotkey({
            id: "command-palette-ctrl",
            keys: "ctrl+k",
            description: "Open command palette (Windows)",
            category: "system",
            handler: () => setOpen(true),
        });

        return () => {
            unregisterCmd();
            unregisterCtrl();
        };
    }, [setOpen]);

    // Close on escape
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === "Escape" && isOpen) {
                setOpen(false);
            }
        };

        window.addEventListener("keydown", handleEscape);
        return () => window.removeEventListener("keydown", handleEscape);
    }, [isOpen, setOpen]);

    // Reset search on close
    useEffect(() => {
        if (!isOpen) {
            setSearch("");
        }
    }, [isOpen]);

    const allCommands = [...defaultCommands, ...commands];

    // Group commands by category
    const groupedCommands = allCommands.reduce(
        (acc, cmd) => {
            acc[cmd.category] = acc[cmd.category] || [];
            acc[cmd.category].push(cmd);
            return acc;
        },
        {} as Record<CommandItem["category"], CommandItem[]>,
    );

    const categoryLabels: Record<CommandItem["category"], string> = {
        navigation: "Navigation",
        actions: "Actions",
        view: "View",
        system: "System",
    };

    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
            aria-label="Command palette"
        >
            {/* Backdrop */}
            <div
                className="absolute inset-0 psd-glass"
                style={{ background: "rgba(0, 0, 0, 0.6)" }}
                onClick={() => setOpen(false)}
                aria-hidden="true"
            />

            {/* Command Dialog */}
            <Command
                className="relative z-10 w-full max-w-lg overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl psd-transition"
                loop
                shouldFilter={true}
            >
                {/* Search Input */}
                <div className="flex items-center border-b border-slate-700 px-4">
                    <Command.Input
                        value={search}
                        onValueChange={setSearch}
                        placeholder="Type a command or search..."
                        className="flex-1 bg-transparent py-4 text-base text-slate-100 placeholder:text-slate-500 focus:outline-none"
                        autoFocus
                    />
                    <button
                        type="button"
                        onClick={() => setOpen(false)}
                        className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
                        aria-label="Close command palette"
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Results */}
                <Command.List className="max-h-80 overflow-y-auto px-2 py-2">
                    <Command.Empty className="py-6 text-center text-sm text-slate-500">
                        No results found.
                    </Command.Empty>

                    {(Object.keys(groupedCommands) as CommandItem["category"][]).map((category) => {
                        const items = groupedCommands[category];
                        if (!items?.length) return null;

                        return (
                            <Command.Group
                                key={category}
                                heading={categoryLabels[category]}
                                className="mb-2"
                            >
                                <div className="mb-1 px-2 text-xs font-medium uppercase tracking-wider text-slate-500">
                                    {categoryLabels[category]}
                                </div>
                                {items.map((cmd) => (
                                    <Command.Item
                                        key={cmd.id}
                                        value={`${cmd.label} ${cmd.description || ""}`}
                                        onSelect={() => {
                                            cmd.onSelect();
                                            setOpen(false);
                                        }}
                                        className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-slate-300 aria-selected:bg-slate-800 aria-selected:text-slate-100"
                                    >
                                        {cmd.icon && (
                                            <span className="flex-shrink-0 text-slate-500">
                                                {cmd.icon}
                                            </span>
                                        )}
                                        <div className="flex-1">
                                            <div className="text-sm font-medium">{cmd.label}</div>
                                            {cmd.description && (
                                                <div className="text-xs text-slate-500">
                                                    {cmd.description}
                                                </div>
                                            )}
                                        </div>
                                        {cmd.shortcut && (
                                            <kbd className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                                                {formatKeyCombo(cmd.shortcut)}
                                            </kbd>
                                        )}
                                    </Command.Item>
                                ))}
                            </Command.Group>
                        );
                    })}
                </Command.List>

                {/* Footer */}
                <div className="flex items-center justify-between border-t border-slate-700 px-4 py-2 text-xs text-slate-500">
                    <span>
                        <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">↑↓</kbd>
                        {" "}to navigate
                    </span>
                    <span>
                        <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">↵</kbd>
                        {" "}to select
                    </span>
                    <span>
                        <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">esc</kbd>
                        {" "}to close
                    </span>
                </div>
            </Command>
        </div>
    );
}

export default PsdCommandPalette;

