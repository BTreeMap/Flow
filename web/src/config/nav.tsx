import { MessageCircle, Bell, Settings, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
    to: string;
    Icon: LucideIcon;
    label: string;
    testId: string;
    /** Path prefixes considered "active" for this item. Defaults to [to]. */
    match?: string[];
    adminOnly?: boolean;
}

/**
 * Single source of truth for primary navigation. Consumed by both the
 * portrait BottomNav (horizontal tabs) and the desktop NavRail (vertical
 * rail) so the two renderers can differ visually without the item data
 * drifting out of sync.
 */
export const NAV_ITEMS: readonly NavItem[] = [
    {
        to: "/dashboard",
        Icon: MessageCircle,
        label: "Chats",
        testId: "nav-chats",
        match: ["/dashboard", "/p/"],
    },
    {
        to: "/updates",
        Icon: Bell,
        label: "Updates",
        testId: "nav-updates",
        match: ["/updates"],
    },
    {
        to: "/settings",
        Icon: Settings,
        label: "Settings",
        testId: "nav-settings",
        match: ["/settings"],
    },
    {
        to: "/admin",
        Icon: ShieldCheck,
        label: "Admin",
        testId: "nav-admin",
        match: ["/admin"],
        adminOnly: true,
    },
];

export function isNavItemActive(item: NavItem, pathname: string): boolean {
    return (item.match ?? [item.to]).some((m) => pathname.startsWith(m));
}
