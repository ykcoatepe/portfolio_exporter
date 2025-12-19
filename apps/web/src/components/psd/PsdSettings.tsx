import type { ReactNode } from "react";
import { Monitor, Moon, Sparkles, Volume2, VolumeX } from "lucide-react";
import clsx from "clsx";

import { usePsdPreferences } from "../../state/psdPreferencesStore";

/**
 * PSD Settings Panel
 *
 * Controls for accessibility and display preferences.
 * Can be rendered as a modal or inline panel.
 */

interface PsdSettingsProps {
    className?: string;
}

export function PsdSettings({ className }: PsdSettingsProps) {
    const {
        reducedMotion,
        reducedTranslucency,
        setReducedMotion,
        setReducedTranslucency,
    } = usePsdPreferences();

    return (
        <div
            className={clsx(
                "rounded-2xl border border-slate-800/60 bg-slate-900 p-6",
                className,
            )}
            role="region"
            aria-label="Display settings"
        >
            <h2 className="mb-6 text-lg font-semibold text-slate-100">
                Display Settings
            </h2>

            <div className="space-y-6">
                {/* Reduced Motion */}
                <SettingToggle
                    id="reduced-motion"
                    label="Reduce Motion"
                    description="Minimize animations and transitions"
                    icon={reducedMotion ? <VolumeX size={20} /> : <Volume2 size={20} />}
                    checked={reducedMotion}
                    onChange={setReducedMotion}
                />

                {/* Reduced Translucency */}
                <SettingToggle
                    id="reduced-translucency"
                    label="Reduce Translucency"
                    description="Use solid backgrounds instead of blur effects"
                    icon={reducedTranslucency ? <Monitor size={20} /> : <Sparkles size={20} />}
                    checked={reducedTranslucency}
                    onChange={setReducedTranslucency}
                />

                {/* Theme (placeholder for future) */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
                            <Moon size={20} />
                        </span>
                        <div>
                            <div className="text-sm font-medium text-slate-200">Theme</div>
                            <div className="text-xs text-slate-500">Dark mode only</div>
                        </div>
                    </div>
                    <span className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-500">
                        Coming soon
                    </span>
                </div>
            </div>
        </div>
    );
}

interface SettingToggleProps {
    id: string;
    label: string;
    description: string;
    icon: ReactNode;
    checked: boolean;
    onChange: (value: boolean) => void;
}

function SettingToggle({
    id,
    label,
    description,
    icon,
    checked,
    onChange,
}: SettingToggleProps) {
    const labelId = `${id}-label`;
    const descId = `${id}-desc`;

    return (
        <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-800 text-slate-400">
                    {icon}
                </span>
                <div>
                    <span id={labelId} className="text-sm font-medium text-slate-200">
                        {label}
                    </span>
                    <div id={descId} className="text-xs text-slate-500">{description}</div>
                </div>
            </div>

            {/* Toggle Switch - using aria-labelledby for accessible name */}
            <button
                type="button"
                role="switch"
                aria-checked={checked}
                aria-labelledby={labelId}
                aria-describedby={descId}
                onClick={() => onChange(!checked)}
                className={clsx(
                    "relative h-6 w-11 rounded-full psd-transition",
                    checked ? "bg-sky-500" : "bg-slate-700",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900",
                )}
            >
                <span
                    className={clsx(
                        "absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow psd-transition",
                        checked && "translate-x-5",
                    )}
                />
            </button>
        </div>
    );
}

export default PsdSettings;

