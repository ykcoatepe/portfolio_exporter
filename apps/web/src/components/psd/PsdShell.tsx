import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { initHotkeys, isMac, registerHotkey } from "../../lib/hotkeys";
import { initPreferencesFromSystem } from "../../state/psdPreferencesStore";
import { HotkeysHelp } from "./HotkeysHelp";
import PsdCommandPalette from "./PsdCommandPalette";
import { PsdSettings } from "./PsdSettings";
import PsdSidebar from "./PsdSidebar";

/**
 * PSD Shell
 *
 * Main application shell providing:
 * - Sidebar navigation
 * - Command palette (Cmd+K)
 * - Settings modal (Cmd+,)
 * - Help modal (?)
 * - Content area for child components
 *
 * This component initializes the hotkey system and preferences on mount.
 */

interface PsdShellProps {
    children: ReactNode;
}

export function PsdShell({ children }: PsdShellProps) {
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [helpOpen, setHelpOpen] = useState(false);

    // Initialize systems on mount
    useEffect(() => {
        initPreferencesFromSystem();
        const cleanupHotkeys = initHotkeys();

        // Register ? hotkey for help
        const unregisterHelp = registerHotkey({
            id: "help-modal",
            keys: "?",
            description: "Show keyboard shortcuts",
            category: "system",
            handler: () => setHelpOpen(true),
        });

        return () => {
            cleanupHotkeys();
            unregisterHelp();
        };
    }, []);

    return (
        <div className="flex h-screen overflow-hidden bg-slate-950">
            {/* Sidebar */}
            <PsdSidebar onSettingsClick={() => setSettingsOpen(true)} />

            {/* Main Content */}
            <div className="flex flex-1 flex-col overflow-hidden">
                {/* Header Bar */}
                <header className="flex h-14 items-center justify-between border-b border-slate-800/60 bg-slate-950/80 px-6">
                    <div className="flex items-center gap-4">
                        <h1 className="text-xl font-semibold tracking-tight text-slate-100">
                            Portfolio Sentinel Dashboard
                        </h1>
                        <span className="rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1 text-xs uppercase tracking-wide text-slate-400">
                            Preview
                        </span>
                    </div>

                    {/* Command Palette Trigger Hint */}
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                        <span>Press</span>
                        <kbd className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                            {isMac() ? "⌘K" : "Ctrl+K"}
                        </kbd>
                        <span>for commands</span>
                    </div>
                </header>

                {/* Scrollable Content Area */}
                <main className="flex-1 overflow-y-auto scroll-smooth">
                    {children}
                </main>
            </div>

            {/* Command Palette (global overlay) */}
            <PsdCommandPalette
                onOpenSettings={() => setSettingsOpen(true)}
                onOpenHelp={() => setHelpOpen(true)}
            />

            {/* Settings Modal */}
            {settingsOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center">
                    <div
                        className="absolute inset-0"
                        style={{ background: "rgba(0, 0, 0, 0.6)" }}
                        onClick={() => setSettingsOpen(false)}
                        aria-hidden="true"
                    />
                    <div className="relative z-10 w-full max-w-md">
                        <button
                            type="button"
                            onClick={() => setSettingsOpen(false)}
                            className="absolute -right-2 -top-2 rounded-full bg-slate-800 p-1.5 text-slate-400 hover:text-slate-200"
                            aria-label="Close settings"
                        >
                            <X size={16} />
                        </button>
                        <PsdSettings />
                    </div>
                </div>
            )}

            {/* Help Modal */}
            <HotkeysHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
        </div>
    );
}

export default PsdShell;

