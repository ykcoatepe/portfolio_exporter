import type { ReactNode } from "react";
import { useEffect } from "react";

import { initHotkeys } from "../../lib/hotkeys";
import { initPreferencesFromSystem, usePsdPreferences } from "../../state/psdPreferencesStore";
import PsdCommandPalette from "./PsdCommandPalette";
import PsdSidebar from "./PsdSidebar";

/**
 * PSD Shell
 *
 * Main application shell providing:
 * - Sidebar navigation
 * - Command palette (Cmd+K)
 * - Content area for child components
 *
 * This component initializes the hotkey system and preferences on mount.
 */

interface PsdShellProps {
    children: ReactNode;
}

export function PsdShell({ children }: PsdShellProps) {
    const { sidebarCollapsed } = usePsdPreferences();

    // Initialize systems on mount
    useEffect(() => {
        initPreferencesFromSystem();
        const cleanupHotkeys = initHotkeys();

        return () => {
            cleanupHotkeys();
        };
    }, []);

    return (
        <div className="flex h-screen overflow-hidden bg-slate-950">
            {/* Sidebar */}
            <PsdSidebar />

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
                            ⌘K
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
            <PsdCommandPalette />
        </div>
    );
}

export default PsdShell;
