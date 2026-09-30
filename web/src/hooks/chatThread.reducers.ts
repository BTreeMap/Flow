import type { FeedbackPollMetadata } from "../api/types";
import {
    debugInfoFromMetadata,
    isSystemContent,
    shouldGroup,
    type DebugInfo,
    type GroupedMessage,
    type Message,
} from "./chatThread.types";

export interface FinalPayload {
    message_id: number;
    server_msg_id: string;
    role: "user" | "assistant";
    content: string;
    metadata?: FeedbackPollMetadata | Record<string, unknown>;
    created_at?: string;
    debug_info?: DebugInfo;
}

export interface ChunkPayload {
    server_msg_id: string;
    delta: string;
}

export interface MetadataPayload {
    message_id: number;
    server_msg_id?: string;
    metadata: FeedbackPollMetadata | Record<string, unknown>;
}

export interface SendResponse {
    message_id: number;
    server_msg_id: string;
    role: "user" | "assistant";
    content: string;
    user_message?: {
        message_id: number;
        server_msg_id: string;
        role: "user" | "assistant";
        content: string;
        created_at: string;
    };
    debug_info?: DebugInfo;
}

/** Upsert a finalized message (replacing any in-flight stream placeholder). */
export function upsertFinalMessage(
    prev: Message[],
    payload: FinalPayload,
): Message[] {
    if (prev.some((m) => m.serverMsgId === payload.server_msg_id)) {
        return prev.map((m) => {
            if (m.serverMsgId === payload.server_msg_id) {
                return {
                    ...m,
                    id: String(payload.message_id), // Ensure ID is sync
                    content: payload.content,
                    metadata: payload.metadata,
                    isStreaming: false,
                    created_at: payload.created_at,
                    debugInfo:
                        payload.debug_info ?? debugInfoFromMetadata(payload.metadata),
                };
            }
            return m;
        });
    }
    const next: Message = {
        id: String(payload.message_id),
        serverMsgId: payload.server_msg_id,
        role: payload.role,
        content: payload.content,
        metadata: payload.metadata,
        created_at: payload.created_at,
        isStreaming: false,
        debugInfo: payload.debug_info ?? debugInfoFromMetadata(payload.metadata),
    };
    return [...prev, next];
}

/** Append a streaming delta to an existing message or create a placeholder. */
export function applyChunk(prev: Message[], payload: ChunkPayload): Message[] {
    if (prev.some((m) => m.serverMsgId === payload.server_msg_id)) {
        return prev.map((m) => {
            if (m.serverMsgId === payload.server_msg_id) {
                return {
                    ...m,
                    content: m.content + payload.delta,
                    isStreaming: true,
                };
            }
            return m;
        });
    }
    const next: Message = {
        id: `stream-${payload.server_msg_id}`,
        serverMsgId: payload.server_msg_id,
        role: "assistant",
        content: payload.delta,
        created_at: new Date().toISOString(),
        isStreaming: true,
    };
    return [...prev, next];
}

/** Patch a message's metadata, matched by message id or server msg id. */
export function applyMetadataUpdate(
    prev: Message[],
    payload: MetadataPayload,
): Message[] {
    return prev.map((m) => {
        if (m.id === String(payload.message_id)) {
            return { ...m, metadata: payload.metadata };
        }
        if (payload.server_msg_id && m.serverMsgId === payload.server_msg_id) {
            return { ...m, metadata: payload.metadata };
        }
        return m;
    });
}

/** Replace the optimistic temp message with the server's user + assistant messages. */
export function applySendResult(
    prev: Message[],
    tempId: string,
    data: SendResponse,
): Message[] {
    const next = prev.filter((m) => m.id !== tempId);

    if (data.user_message) {
        const userMessage = data.user_message;
        if (!next.some((m) => m.serverMsgId === userMessage.server_msg_id)) {
            next.push({
                id: String(userMessage.message_id),
                serverMsgId: userMessage.server_msg_id,
                role: userMessage.role,
                content: userMessage.content,
                created_at: userMessage.created_at,
            });
        }
    }

    const asstIdx = next.findIndex((m) => m.serverMsgId === data.server_msg_id);
    if (asstIdx !== -1) {
        next[asstIdx] = {
            ...next[asstIdx],
            id: String(data.message_id),
            serverMsgId: data.server_msg_id,
            role: data.role,
            content: data.content,
            created_at: data.user_message?.created_at || new Date().toISOString(),
            isStreaming: false,
            debugInfo: data.debug_info,
        };
    } else {
        next.push({
            id: String(data.message_id),
            serverMsgId: data.server_msg_id,
            role: data.role,
            content: data.content,
            created_at: new Date().toISOString(),
            isStreaming: false,
            debugInfo: data.debug_info,
        });
    }
    return next;
}

/**
 * Sort and group messages for rendering.
 *
 * Order: [ ...Persisted (by numeric id), ...PendingUser (temp-*), ...StreamingAssistant (stream-*) ]
 * so pending/streaming always appear at the bottom until confirmed/persisted. System
 * messages are filtered out, and adjacent same-author messages are grouped.
 */
export function computeGroupedMessages(messages: Message[]): GroupedMessage[] {
    const persisted: Message[] = [];
    const pendingUser: Message[] = [];
    const streamingAssistant: Message[] = [];

    messages.forEach((m) => {
        if (m.id.startsWith("temp-")) {
            pendingUser.push(m);
        } else if (m.id.startsWith("stream-")) {
            streamingAssistant.push(m);
        } else {
            persisted.push(m);
        }
    });

    persisted.sort((a, b) => Number(a.id) - Number(b.id));
    const byCreatedAt = (a: Message, b: Message) =>
        new Date(a.created_at ?? 0).getTime() -
        new Date(b.created_at ?? 0).getTime();
    pendingUser.sort(byCreatedAt);
    streamingAssistant.sort(byCreatedAt);

    const sorted = [...persisted, ...pendingUser, ...streamingAssistant].filter(
        (m) => !isSystemContent(m.content),
    );

    return sorted.map((msg, i) => ({
        ...msg,
        isGroupContinuation: shouldGroup(sorted[i - 1], msg),
    }));
}
