import { describe, it, expect } from "vitest";
import {
    isSystemContent,
    formatBubbleTime,
    shouldGroup,
    debugInfoFromMetadata,
    type Message,
} from "./chatThread.types";
import {
    upsertFinalMessage,
    applyChunk,
    applyMetadataUpdate,
    applySendResult,
    computeGroupedMessages,
} from "./chatThread.reducers";

function msg(over: Partial<Message> & { id: string }): Message {
    return {
        serverMsgId: `s-${over.id}`,
        role: "assistant",
        content: "hi",
        ...over,
    };
}

describe("chatThread.types helpers", () => {
    it("isSystemContent detects system markers", () => {
        expect(isSystemContent("[System: x]")).toBe(true);
        expect(isSystemContent("hello")).toBe(false);
    });

    it("formatBubbleTime returns undefined for missing time", () => {
        expect(formatBubbleTime(undefined)).toBeUndefined();
        expect(formatBubbleTime(new Date().toISOString())).toMatch(/\d/);
    });

    it("shouldGroup groups same-author messages within 2 minutes", () => {
        const a = msg({ id: "1", created_at: "2024-01-01T00:00:00.000Z" });
        const b = msg({ id: "2", created_at: "2024-01-01T00:01:00.000Z" });
        expect(shouldGroup(a, b)).toBe(true);
    });

    it("shouldGroup does not group across authors or large gaps", () => {
        const a = msg({ id: "1", role: "user", created_at: "2024-01-01T00:00:00.000Z" });
        const b = msg({ id: "2", role: "assistant", created_at: "2024-01-01T00:01:00.000Z" });
        expect(shouldGroup(a, b)).toBe(false);
        const c = msg({ id: "3", created_at: "2024-01-01T00:00:00.000Z" });
        const d = msg({ id: "4", created_at: "2024-01-01T00:05:00.000Z" });
        expect(shouldGroup(c, d)).toBe(false);
    });

    it("debugInfoFromMetadata extracts nested debug_info", () => {
        expect(debugInfoFromMetadata(undefined)).toBeUndefined();
        expect(debugInfoFromMetadata({})).toBeUndefined();
        expect(
            debugInfoFromMetadata({ debug_info: { agent: "coach" } }),
        ).toEqual({ agent: "coach" });
    });
});

describe("upsertFinalMessage", () => {
    it("appends a new finalized message", () => {
        const out = upsertFinalMessage([], {
            message_id: 1,
            server_msg_id: "s1",
            role: "assistant",
            content: "done",
        });
        expect(out).toHaveLength(1);
        expect(out[0]).toMatchObject({ id: "1", content: "done", isStreaming: false });
    });

    it("replaces an in-flight stream placeholder by serverMsgId", () => {
        const prev: Message[] = [
            { id: "stream-s1", serverMsgId: "s1", role: "assistant", content: "par", isStreaming: true },
        ];
        const out = upsertFinalMessage(prev, {
            message_id: 9,
            server_msg_id: "s1",
            role: "assistant",
            content: "partial complete",
        });
        expect(out).toHaveLength(1);
        expect(out[0]).toMatchObject({ id: "9", content: "partial complete", isStreaming: false });
    });
});

describe("applyChunk", () => {
    it("creates a streaming placeholder when none exists", () => {
        const out = applyChunk([], { server_msg_id: "s1", delta: "He" });
        expect(out[0]).toMatchObject({ id: "stream-s1", content: "He", isStreaming: true });
    });

    it("appends delta to existing message", () => {
        const prev = applyChunk([], { server_msg_id: "s1", delta: "He" });
        const out = applyChunk(prev, { server_msg_id: "s1", delta: "llo" });
        expect(out[0]?.content).toBe("Hello");
    });
});

describe("applyMetadataUpdate", () => {
    it("patches metadata by message id", () => {
        const prev: Message[] = [msg({ id: "5" })];
        const out = applyMetadataUpdate(prev, {
            message_id: 5,
            metadata: { kind: "feedback_poll" } as Record<string, unknown>,
        });
        expect(out[0]?.metadata).toEqual({ kind: "feedback_poll" });
    });
});

describe("applySendResult", () => {
    it("replaces temp message with user + assistant messages", () => {
        const prev: Message[] = [
            { id: "temp-1", serverMsgId: "temp-1", role: "user", content: "hi" },
        ];
        const out = applySendResult(prev, "temp-1", {
            message_id: 11,
            server_msg_id: "a1",
            role: "assistant",
            content: "reply",
            user_message: {
                message_id: 10,
                server_msg_id: "u1",
                role: "user",
                content: "hi",
                created_at: "2024-01-01T00:00:00.000Z",
            },
        });
        expect(out.some((m) => m.id === "temp-1")).toBe(false);
        expect(out.map((m) => m.id)).toEqual(["10", "11"]);
    });
});

describe("computeGroupedMessages", () => {
    it("orders persisted then pending then streaming and drops system content", () => {
        const messages: Message[] = [
            msg({ id: "2", role: "user", content: "second" }),
            msg({ id: "1", role: "user", content: "first" }),
            msg({ id: "temp-9", serverMsgId: "temp-9", role: "user", content: "pending", created_at: "2024-01-01T00:00:00.000Z" }),
            msg({ id: "stream-x", serverMsgId: "x", content: "streaming", created_at: "2024-01-01T00:00:01.000Z" }),
            msg({ id: "3", role: "assistant", content: "[System: hidden]" }),
        ];
        const grouped = computeGroupedMessages(messages);
        expect(grouped.map((m) => m.content)).toEqual([
            "first",
            "second",
            "pending",
            "streaming",
        ]);
    });

    it("marks adjacent same-author messages as continuations", () => {
        const grouped = computeGroupedMessages([
            msg({ id: "1", role: "user", content: "a", created_at: "2024-01-01T00:00:00.000Z" }),
            msg({ id: "2", role: "user", content: "b", created_at: "2024-01-01T00:00:30.000Z" }),
        ]);
        expect(grouped[0]?.isGroupContinuation).toBe(false);
        expect(grouped[1]?.isGroupContinuation).toBe(true);
    });
});
