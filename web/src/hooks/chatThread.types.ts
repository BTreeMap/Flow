import type { FeedbackPollMetadata } from "../api/types";

export interface ToolCall {
    run_id?: string;
    tool?: string;
    args?: unknown;
    error?: string;
}

export interface DebugInfo {
    agent?: string;
    condition?: string;
    prompt_args?: Record<string, unknown>;
    tools?: string[];
    tool_calls?: ToolCall[];
}

export interface Message {
    id: string;
    serverMsgId: string;
    role: "user" | "assistant";
    content: string;
    metadata?: FeedbackPollMetadata | Record<string, unknown>;
    created_at?: string;
    isStreaming?: boolean;
    debugInfo?: DebugInfo;
}

export interface RawMessage {
    message_id: number;
    server_msg_id: string;
    role: "user" | "assistant";
    content: string;
    metadata?: FeedbackPollMetadata | Record<string, unknown>;
    created_at?: string;
    debug_info?: DebugInfo;
}

export type GroupedMessage = Message & { isGroupContinuation: boolean };

export function isSystemContent(content: string): boolean {
    return content.startsWith("[System:");
}

export function formatBubbleTime(iso?: string): string | undefined {
    if (!iso) return undefined;
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function shouldGroup(
    prev: Message | undefined,
    curr: Message,
): boolean {
    if (prev?.role !== curr.role) return false;
    if (!prev.created_at || !curr.created_at) return false;
    const diff =
        new Date(curr.created_at).getTime() - new Date(prev.created_at).getTime();
    return diff < 2 * 60 * 1000; // 2 minutes
}

export function debugInfoFromMetadata(
    metadata: FeedbackPollMetadata | Record<string, unknown> | undefined,
): DebugInfo | undefined {
    if (!metadata || typeof metadata !== "object") return undefined;
    const debugInfo = (metadata as Record<string, unknown>).debug_info;
    if (!debugInfo || typeof debugInfo !== "object") return undefined;
    return debugInfo as DebugInfo;
}
