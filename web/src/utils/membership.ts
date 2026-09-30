import type { MembershipInfo } from "../api/types";

export function getDisplayPreview(
    preview: string | null | undefined,
): string {
    if (!preview) return "No messages yet";
    return preview.startsWith("[System:") ? "Feedback submitted" : preview;
}

function getLastOpenedAt(projectId: string): string | null {
    return localStorage.getItem(`chat-opened:${projectId}`);
}

export function isUnread(m: MembershipInfo): boolean {
    if (!m.last_message_at) return false;
    const opened = getLastOpenedAt(m.project_id);
    if (!opened) return true;
    return m.last_message_at > opened;
}

export function formatTime(iso: string): string {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function sortMemberships(memberships: MembershipInfo[] | undefined) {
    const mbs = memberships ?? [];
    const active = mbs.filter((m) => m.status === "active");
    const ended = mbs.filter((m) => m.status !== "active");

    // Sort active memberships by last_message_at descending
    active.sort((a, b) => {
        const aT = a.last_message_at ?? "";
        const bT = b.last_message_at ?? "";
        return bT.localeCompare(aT);
    });

    return { active, ended };
}

export function filterMemberships(
    sorted: { active: MembershipInfo[]; ended: MembershipInfo[] },
    search: string,
) {
    const { active, ended } = sorted;

    if (!search.trim()) return { active, ended };
    const q = search.toLowerCase();
    return {
        active: active.filter(
            (m) =>
                (m.display_name ?? "").toLowerCase().includes(q) ||
                (m.last_message_preview ?? "").toLowerCase().includes(q),
        ),
        ended: ended.filter((m) =>
            (m.display_name ?? "").toLowerCase().includes(q),
        ),
    };
}
