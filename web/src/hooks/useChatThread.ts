import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useQueryClient } from "@tanstack/react-query";
import { getOrMintToken } from "../auth/token";
import type { DashboardResponse } from "../api/types";
import api from "../api/client";
import {
    debugInfoFromMetadata,
    type GroupedMessage,
    type Message,
    type RawMessage,
} from "./chatThread.types";
import {
    applyChunk,
    applyMetadataUpdate,
    applySendResult,
    computeGroupedMessages,
    upsertFinalMessage,
    type ChunkPayload,
    type FinalPayload,
    type MetadataPayload,
    type SendResponse,
} from "./chatThread.reducers";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export type ConnectionStatus = "online" | "reconnecting" | "offline";

export interface ChatThread {
    messages: Message[];
    groupedMessages: GroupedMessage[];
    loading: boolean;
    sending: boolean;
    error: string | null;
    connectionStatus: ConnectionStatus;
    chatTitle: string;
    sendMessage: (text: string) => Promise<void>;
}

export function useChatThread(projectId: string | undefined): ChatThread {
    const [searchParams, setSearchParams] = useSearchParams();
    const queryClient = useQueryClient();
    const [messages, setMessages] = useState<Message[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [connectionStatus, setConnectionStatus] =
        useState<ConnectionStatus>("online");
    const [currentNotificationId, setCurrentNotificationId] = useState<
        number | null
    >(null);
    const lastEventIdRef = useRef<string | null>(null);
    const [chatTitle, setChatTitle] = useState("Chat");
    const [sending, setSending] = useState(false);

    // Mark chat as opened for unread tracking
    useEffect(() => {
        if (projectId) {
            localStorage.setItem(
                `chat-opened:${projectId}`,
                new Date().toISOString(),
            );
        }
    }, [projectId]);

    // Handle push notification interaction (nid param)
    useEffect(() => {
        const nid = searchParams.get("nid");
        const parsedNid = nid ? parseInt(nid, 10) : NaN;
        if (!Number.isNaN(parsedNid) && projectId) {
            // Safe to carry this id client-side: backend re-verifies user+membership scope
            // before cancelling any scheduled feedback task.
            setCurrentNotificationId(parsedNid);
            // Clear param immediately so we don't re-trigger
            const newParams = new URLSearchParams(searchParams);
            newParams.delete("nid");
            setSearchParams(newParams, { replace: true });

            // Call mark-read (unified global endpoint)
            void (async () => {
                try {
                    await api.POST("/notifications/{notification_id}/read", {
                        params: {
                            path: {
                                notification_id: parsedNid,
                            },
                        },
                    });
                } catch (err) {
                    console.error("Failed to mark notification read", err);
                }
            })();
        }
    }, [projectId, searchParams, setSearchParams]);

    // Load existing messages
    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const token = await getOrMintToken("http");

                // Fetch dashboard for chat title
                const dashRes = await fetch(`${API_BASE}/dashboard`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (dashRes.ok) {
                    const dashData = (await dashRes.json()) as {
                        memberships?: { project_id: string; display_name?: string }[];
                    };
                    const membership = (dashData.memberships ?? []).find(
                        (m) => m.project_id === projectId,
                    );
                    if (membership?.display_name) {
                        setChatTitle(membership.display_name);
                    }
                }

                const res = await fetch(`${API_BASE}/p/${projectId}/messages`, {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok) throw new Error(`Failed to load messages (${res.status})`);
                const data = (await res.json()) as { messages?: RawMessage[] };
                if (!cancelled) {
                    setMessages(
                        (data.messages ?? []).map((msg) => ({
                            id: String(msg.message_id),
                            serverMsgId: msg.server_msg_id,
                            role: msg.role,
                            content: msg.content,
                            metadata: msg.metadata,
                            created_at: msg.created_at,
                            debugInfo: msg.debug_info ?? debugInfoFromMetadata(msg.metadata),
                        })),
                    );
                    setLoading(false);
                }
            } catch (err) {
                if (!cancelled) {
                    setError(
                        err instanceof Error ? err.message : "Failed to load messages",
                    );
                    setLoading(false);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [projectId]);

    // Update dashboard helper
    const updateDashboardPreview = useCallback(
        (preview: string, timestamp?: string) => {
            queryClient.setQueryData<DashboardResponse>(["dashboard"], (old) => {
                if (!old || !projectId) return old;
                return {
                    ...old,
                    memberships: old.memberships.map((m) => {
                        if (m.project_id === projectId) {
                            return {
                                ...m,
                                last_message_preview: preview,
                                last_message_at: timestamp || m.last_message_at, // Keep old time if pending
                            };
                        }
                        return m;
                    }),
                };
            });
        },
        [projectId, queryClient],
    );

    // SSE connection for real-time updates
    useEffect(() => {
        const ctrl = new AbortController();
        let active = true;

        const appendSSEMessage = (payload: FinalPayload) => {
            setMessages((prev) => upsertFinalMessage(prev, payload));
            // Locally update dashboard
            updateDashboardPreview(payload.content, payload.created_at);
        };

        const handleSSEChunk = (payload: ChunkPayload) => {
            setMessages((prev) => applyChunk(prev, payload));
        };

        const handleMessageUpdated = (payload: MetadataPayload) => {
            setMessages((prev) => applyMetadataUpdate(prev, payload));
        };

        void (async () => {
            let retryCount = 0;
            while (active && !ctrl.signal.aborted) {
                try {
                    const token = await getOrMintToken("sse");
                    if (retryCount > 0) {
                        setConnectionStatus("reconnecting");
                    }
                    await fetchEventSource(`${API_BASE}/p/${projectId}/events`, {
                        headers: {
                            Authorization: `Bearer ${token}`,
                            ...(lastEventIdRef.current
                                ? { "Last-Event-ID": lastEventIdRef.current }
                                : {}),
                        },
                        signal: ctrl.signal,
                        onmessage(ev) {
                            if (ev.id) {
                                lastEventIdRef.current = ev.id;
                            }
                            if (ev.event === "message.final") {
                                try {
                                    appendSSEMessage(JSON.parse(ev.data) as FinalPayload);
                                } catch (err) {
                                    console.warn("Discarding malformed message.final SSE", err);
                                }
                            } else if (ev.event === "message.updated") {
                                try {
                                    handleMessageUpdated(JSON.parse(ev.data) as MetadataPayload);
                                } catch (err) {
                                    console.warn("Discarding malformed message.updated SSE", err);
                                }
                            } else if (ev.event === "message.chunk") {
                                try {
                                    handleSSEChunk(JSON.parse(ev.data) as ChunkPayload);
                                } catch (err) {
                                    console.warn("Discarding malformed message.chunk SSE", err);
                                }
                            }
                        },
                        onopen(response) {
                            if (!response.ok) {
                                if (response.status === 401 || response.status === 403) {
                                    setError("Your session expired. Please log in again.");
                                    ctrl.abort();
                                    throw new Error("auth");
                                }
                                throw new Error(`SSE connection failed (${response.status})`);
                            }
                            retryCount = 0;
                            setConnectionStatus("online");
                            return Promise.resolve();
                        },
                        openWhenHidden: true,
                    });
                } catch {
                    if (!active || ctrl.signal.aborted) {
                        return;
                    }
                    setConnectionStatus("reconnecting");
                    retryCount += 1;
                    const backoffMs = Math.min(1000 * 2 ** (retryCount - 1), 10000);
                    await new Promise((resolve) => setTimeout(resolve, backoffMs));
                }
            }
        })();

        return () => {
            active = false;
            ctrl.abort();
        };
    }, [projectId, queryClient, updateDashboardPreview]);

    const sendMessage = useCallback(
        async (text: string) => {
            if (!text || sending) return;

            setSending(true);
            setError(null);

            const tempId = `temp-${Date.now()}`;
            const userMsg: Message = {
                id: tempId,
                serverMsgId: tempId,
                role: "user",
                content: text,
                created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, userMsg]);

            // Optimistically update dashboard
            updateDashboardPreview(text, userMsg.created_at);

            try {
                const token = await getOrMintToken("http");
                const res = await fetch(`${API_BASE}/p/${projectId}/messages`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        text,
                        client_msg_id: tempId,
                        current_notification_id: currentNotificationId,
                    }),
                });

                if (!res.ok) {
                    if (res.status === 401 || res.status === 403) {
                        throw new Error("Your session expired. Please log in again.");
                    }
                    throw new Error(`Send failed (${res.status})`);
                }

                const data = (await res.json()) as SendResponse;
                setMessages((prev) => applySendResult(prev, tempId, data));
                // Locally update dashboard with final assistant message
                updateDashboardPreview(data.content);
                setCurrentNotificationId(null);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to send message");
                setMessages((prev) => prev.filter((m) => m.id !== tempId));
            } finally {
                setSending(false);
                // Update last opened
                if (projectId) {
                    localStorage.setItem(
                        `chat-opened:${projectId}`,
                        new Date().toISOString(),
                    );
                }
            }
        },
        [sending, projectId, currentNotificationId, updateDashboardPreview],
    );

    const groupedMessages = useMemo<GroupedMessage[]>(
        () => computeGroupedMessages(messages),
        [messages],
    );

    return {
        messages,
        groupedMessages,
        loading,
        sending,
        error,
        connectionStatus,
        chatTitle,
        sendMessage,
    };
}
