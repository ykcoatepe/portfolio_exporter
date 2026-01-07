import type { ReactNode } from "react";
import clsx from "clsx";
import {
    BarChart3,
    ChevronLeft,
    ChevronRight,
    LayoutDashboard,
    Settings,
    Shield,
    Table2,
} from "lucide-react";

import { usePsdPreferences } from "../../state/psdPreferencesStore";

/**
 * PSD Sidebar
 *
 * Collapsible navigation sidebar for the dashboard.
 * Uses glass effect per design system (framing UI).
 */

interface NavItem {
    id: string;
    label: string;
    icon: ReactNode;
    onClick?: () => void;
}

interface PsdSidebarProps {
    className?: string;
    onSettingsClick?: () => void;
}

export function PsdSidebar({ className, onSettingsClick }: PsdSidebarProps) {
    const { sidebarCollapsed, toggleSidebar } = usePsdPreferences();

    const navItems: NavItem[] = [
        {
            id: "dashboard",
            label: "Dashboard",
            icon: <LayoutDashboard size={20} />,
            onClick: () => {
                document.querySelector('[aria-label="Portfolio Sentinel sections"]')?.scrollIntoView({ behavior: "auto" });
            },
        },
        {
            id: "positions",
            label: "Positions",
            icon: <Table2 size={20} />,
            onClick: () => {
                document.querySelector('[aria-label="Single Stocks"]')?.scrollIntoView({ behavior: "auto" });
            },
        },
        {
            id: "charts",
            label: "Charts",
            icon: <BarChart3 size={20} />,
            onClick: () => {
                document.querySelector('[aria-label="Market Stress Barometer overview"]')?.scrollIntoView({ behavior: "auto" });
            },
        },
        {
            id: "sentinel",
            label: "Sentinel",
            icon: <Shield size={20} />,
            onClick: () => {
                document.querySelector('[aria-label="Rules & Fundamentals"]')?.scrollIntoView({ behavior: "auto" });
            },
        },
    ];

    const bottomItems: NavItem[] = [
        {
            id: "settings",
            label: "Settings",
            icon: <Settings size={20} />,
            onClick: onSettingsClick,
        },
    ];

    return (
        <aside
            className={clsx(
                "flex h-full flex-col border-r psd-glass psd-transition",
                sidebarCollapsed ? "w-16" : "w-56",
                "border-slate-800/60",
                className,
            )}
            aria-label="Main navigation"
        >
            {/* Header */}
            <div className="flex h-16 items-center justify-between border-b border-slate-800/60 px-4">
                {!sidebarCollapsed && (
                    <span className="text-lg font-semibold text-slate-100">PSD</span>
                )}
                <button
                    type="button"
                    onClick={toggleSidebar}
                    className={clsx(
                        "rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-200 psd-transition",
                        sidebarCollapsed && "mx-auto",
                    )}
                    aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                >
                    {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
                </button>
            </div>

            {/* Main Nav */}
            <nav className="flex-1 space-y-1 px-2 py-4" aria-label="Primary">
                {navItems.map((item) => (
                    <NavButton key={item.id} item={item} collapsed={sidebarCollapsed} />
                ))}
            </nav>

            {/* Bottom Nav */}
            <nav className="border-t border-slate-800/60 px-2 py-4" aria-label="Secondary">
                {bottomItems.map((item) => (
                    <NavButton key={item.id} item={item} collapsed={sidebarCollapsed} />
                ))}
            </nav>
        </aside>
    );
}

interface NavButtonProps {
    item: NavItem;
    collapsed: boolean;
}

function NavButton({ item, collapsed }: NavButtonProps) {
    return (
        <button
            type="button"
            onClick={item.onClick}
            className={clsx(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-slate-400 psd-transition",
                "hover:bg-slate-800/80 hover:text-slate-200",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                collapsed && "justify-center px-2",
            )}
            title={collapsed ? item.label : undefined}
            aria-label={collapsed ? item.label : undefined}
        >
            <span className="flex-shrink-0">{item.icon}</span>
            {!collapsed && (
                <span className="text-sm font-medium">{item.label}</span>
            )}
        </button>
    );
}

export default PsdSidebar;

