import { useEffect } from "react";
import { X } from "lucide-react";

import {
    formatKeyCombo,
    getHotkeysByCategory,
} from "../../lib/hotkeys";

/**
 * PSD Hotkeys Help Modal
 *
 * Displays all registered keyboard shortcuts grouped by category.
 * Trigger: ? key (registered in PsdShell)
 */

interface HotkeysHelpProps {
    open: boolean;
    onClose: () => void;
}

const categoryLabels: Record<string, string> = {
    navigation: "Navigation",
    actions: "Actions",
    view: "View",
    system: "System",
};

export function HotkeysHelp({ open, onClose }: HotkeysHelpProps) {
    const hotkeysByCategory = getHotkeysByCategory();

    // Close on escape
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === "Escape" && open) {
                onClose();
            }
        };

        window.addEventListener("keydown", handleEscape);
        return () => window.removeEventListener("keydown", handleEscape);
    }, [open, onClose]);

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            aria-label="Keyboard shortcuts"
            role="dialog"
            aria-modal="true"
        >
            {/* Backdrop */}
            <div
                className="absolute inset-0"
                style={{ background: "rgba(0, 0, 0, 0.6)" }}
                onClick={onClose}
                aria-hidden="true"
            />

            {/* Modal */}
            <div className="relative z-10 w-full max-w-lg overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
                {/* Header */}
                <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
                    <h2 className="text-lg font-semibold text-slate-100">
                        Keyboard Shortcuts
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
                        aria-label="Close"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="max-h-96 overflow-y-auto px-6 py-4">
                    {Object.entries(hotkeysByCategory).map(([category, hotkeys]) => {
                        if (!hotkeys.length) return null;

                        return (
                            <div key={category} className="mb-6 last:mb-0">
                                <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
                                    {categoryLabels[category] || category}
                                </h3>
                                <div className="space-y-2">
                                    {hotkeys.map((hotkey) => (
                                        <div
                                            key={hotkey.id}
                                            className="flex items-center justify-between"
                                        >
                                            <span className="text-sm text-slate-300">
                                                {hotkey.description}
                                            </span>
                                            <kbd className="rounded bg-slate-800 px-2 py-1 text-xs font-mono text-slate-400">
                                                {formatKeyCombo(hotkey.keys)}
                                            </kbd>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        );
                    })}

                    {/* Static hints for non-registered shortcuts */}
                    <div className="mt-6 border-t border-slate-700 pt-4">
                        <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
                            General
                        </h3>
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <span className="text-sm text-slate-300">Navigate items</span>
                                <div className="flex gap-1">
                                    <kbd className="rounded bg-slate-800 px-2 py-1 text-xs font-mono text-slate-400">
                                        ↑
                                    </kbd>
                                    <kbd className="rounded bg-slate-800 px-2 py-1 text-xs font-mono text-slate-400">
                                        ↓
                                    </kbd>
                                </div>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-sm text-slate-300">Select item</span>
                                <kbd className="rounded bg-slate-800 px-2 py-1 text-xs font-mono text-slate-400">
                                    ↵
                                </kbd>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="text-sm text-slate-300">Close modal</span>
                                <kbd className="rounded bg-slate-800 px-2 py-1 text-xs font-mono text-slate-400">
                                    Esc
                                </kbd>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="border-t border-slate-700 px-6 py-3 text-center text-xs text-slate-500">
                    Press <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-400">?</kbd> anytime to show this help
                </div>
            </div>
        </div>
    );
}

export default HotkeysHelp;

