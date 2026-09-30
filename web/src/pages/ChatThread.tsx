import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router";
import { Alert } from "../components/Alert";
import { useAuth } from "../auth";
import { ChevronDown } from "lucide-react";
import { ChatHeader } from "../components/ui/ChatHeader";
import { MessageBubble } from "../components/ui/MessageBubble";
import { Composer } from "../components/ui/Composer";
import { useLayoutMode } from "../hooks/useLayoutMode";
import { useTimezone } from "../hooks/useTimezone";
import { useChatThread } from "../hooks/useChatThread";
import { formatBubbleTime } from "../hooks/chatThread.types";

export function ChatThread() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  useAuth();
  useTimezone();
  const layoutMode = useLayoutMode();
  const {
    messages,
    groupedMessages,
    loading,
    sending,
    error,
    connectionStatus,
    chatTitle,
    sendMessage,
  } = useChatThread(projectId);

  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const isNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (!showJumpToBottom) {
      scrollToBottom();
    } else {
      // New message arrived while the user is scrolled up: surface the badge.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- event-driven flag, not derivable during render
      setHasNewMessages(true);
    }
  }, [messages, showJumpToBottom, scrollToBottom]);

  // Track scroll position for jump-to-bottom
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const nearBottom = isNearBottom();
      setShowJumpToBottom(!nearBottom);
      if (nearBottom) {
        setHasNewMessages(false);
      }
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", handleScroll);
    };
  }, [isNearBottom]);

  const handleSend = (text: string) => {
    void sendMessage(text);
    setTimeout(() => {
      scrollToBottom();
      setShowJumpToBottom(false);
      setHasNewMessages(false);
    }, 0);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center flex-1 bg-chat-bg">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className={`flex flex-col bg-chat-bg ${layoutMode === "side" ? "h-full" : "flex-1 min-h-0"}`}>
      <ChatHeader
        title={chatTitle}
        hideBack={layoutMode === "side"}
        avatar={
          <div className="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center text-[13px] font-semibold">
            {(chatTitle[0] ?? "C").toUpperCase()}
          </div>
        }
        connectionStatus={connectionStatus}
        menuItems={[
          {
            label: "Updates",
            onClick: () => void navigate(`/p/${projectId}/updates`),
          },
          {
            label: "Notification Settings",
            onClick: () => void navigate(`/p/${projectId}/notifications`),
          },
        ]}
        debugMode={debugMode}
        onToggleDebug={() => { setDebugMode(!debugMode); }}
      />

      {error && (
        <div className="px-3 pt-2">
          <Alert variant="error">{error}</Alert>
        </div>
      )}

      {/* Message list */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-3 py-2"
      >
        {messages.length === 0 && (
          <p className="text-center text-text-muted py-12 text-[14px]">
            No messages yet. Start the conversation!
          </p>
        )}
        {groupedMessages.map((msg) => (
          <MessageBubble
            key={msg.id}
            projectId={projectId}
            role={msg.role}
            content={msg.content}
            metadata={msg.metadata}
            timestamp={formatBubbleTime(msg.created_at)}
            isGroupContinuation={msg.isGroupContinuation}
            isStreaming={msg.isStreaming}
            debugInfo={msg.debugInfo}
            showDebug={debugMode}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Jump to bottom */}
      {showJumpToBottom && (
        <div className="relative z-30">
          <button
            onClick={scrollToBottom}
            className={`absolute bottom-3 right-4 w-10 h-10 rounded-full shadow-md flex items-center justify-center transition-colors ${hasNewMessages
              ? "bg-primary text-primary-foreground hover:bg-primary/90"
              : "bg-surface text-text-muted hover:bg-surface-2"
              }`}
            aria-label="Jump to bottom"
            data-testid="jump-to-bottom"
          >
            <ChevronDown className="w-5 h-5" />
          </button>
        </div>
      )}

      <Composer onSend={handleSend} disabled={sending} />
    </div>
  );
}
