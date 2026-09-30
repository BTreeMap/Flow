import { describe, it, expect, beforeEach, vi } from "vitest";
import type { MembershipInfo } from "../api/types";
import {
    getDisplayPreview,
    isUnread,
    formatTime,
    sortMemberships,
    filterMemberships,
} from "./membership";

function makeMembership(over: Partial<MembershipInfo>): MembershipInfo {
    return {
        project_id: "p-1",
        status: "active",
        display_name: "Project",
        last_message_at: null,
        last_message_preview: null,
        ...over,
    };
}

describe("getDisplayPreview", () => {
    it("returns placeholder when preview is empty", () => {
        expect(getDisplayPreview(null)).toBe("No messages yet");
        expect(getDisplayPreview(undefined)).toBe("No messages yet");
        expect(getDisplayPreview("")).toBe("No messages yet");
    });

    it("masks system feedback previews", () => {
        expect(getDisplayPreview("[System: feedback]")).toBe("Feedback submitted");
    });

    it("passes through normal previews", () => {
        expect(getDisplayPreview("Hello there")).toBe("Hello there");
    });
});

describe("isUnread", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it("is false when there is no last message", () => {
        expect(isUnread(makeMembership({ last_message_at: null }))).toBe(false);
    });

    it("is true when never opened but has a message", () => {
        expect(
            isUnread(
                makeMembership({ last_message_at: "2024-01-01T00:00:00.000Z" }),
            ),
        ).toBe(true);
    });

    it("is false when opened after the last message", () => {
        localStorage.setItem("chat-opened:p-1", "2024-02-01T00:00:00.000Z");
        expect(
            isUnread(
                makeMembership({ last_message_at: "2024-01-01T00:00:00.000Z" }),
            ),
        ).toBe(false);
    });

    it("is true when a message arrived after last open", () => {
        localStorage.setItem("chat-opened:p-1", "2024-01-01T00:00:00.000Z");
        expect(
            isUnread(
                makeMembership({ last_message_at: "2024-02-01T00:00:00.000Z" }),
            ),
        ).toBe(true);
    });
});

describe("formatTime", () => {
    it("shows a clock time for today", () => {
        const now = new Date();
        expect(formatTime(now.toISOString())).toMatch(/\d/);
    });

    it("shows Yesterday for a day-old timestamp", () => {
        const d = new Date(Date.now() - 1000 * 60 * 60 * 24);
        expect(formatTime(d.toISOString())).toBe("Yesterday");
    });
});

describe("sortMemberships", () => {
    it("splits active vs ended and sorts active by recency desc", () => {
        const { active, ended } = sortMemberships([
            makeMembership({
                project_id: "old",
                last_message_at: "2024-01-01T00:00:00.000Z",
            }),
            makeMembership({ project_id: "ended", status: "ended" }),
            makeMembership({
                project_id: "new",
                last_message_at: "2024-03-01T00:00:00.000Z",
            }),
        ]);
        expect(active.map((m) => m.project_id)).toEqual(["new", "old"]);
        expect(ended.map((m) => m.project_id)).toEqual(["ended"]);
    });

    it("handles undefined input", () => {
        expect(sortMemberships(undefined)).toEqual({ active: [], ended: [] });
    });
});

describe("filterMemberships", () => {
    const sorted = {
        active: [
            makeMembership({ project_id: "a", display_name: "Alpha" }),
            makeMembership({
                project_id: "b",
                display_name: "Beta",
                last_message_preview: "special keyword",
            }),
        ],
        ended: [makeMembership({ project_id: "c", display_name: "Gamma", status: "ended" })],
    };

    it("returns all when search is blank", () => {
        expect(filterMemberships(sorted, "  ")).toEqual(sorted);
    });

    it("matches by display name", () => {
        const res = filterMemberships(sorted, "alpha");
        expect(res.active.map((m) => m.project_id)).toEqual(["a"]);
        expect(res.ended).toEqual([]);
    });

    it("matches active by preview but ended only by name", () => {
        const res = filterMemberships(sorted, "keyword");
        expect(res.active.map((m) => m.project_id)).toEqual(["b"]);
        expect(res.ended).toEqual([]);
    });
});

describe("pwa detection", () => {
    it("isStandalone reflects display-mode media query", async () => {
        const { isStandalone } = await import("./pwa");
        vi.stubGlobal(
            "matchMedia",
            vi.fn().mockReturnValue({ matches: true } as MediaQueryList),
        );
        expect(isStandalone()).toBe(true);
        vi.unstubAllGlobals();
    });
});
