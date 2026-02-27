import { memo } from "react";
import { AssistantMarkdown } from "../chat/AssistantMarkdown";
import type { SendMessageResponse } from "../../api/openapi";

interface MessageBubbleProps {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  isGroupContinuation?: boolean;
  isStreaming?: boolean;
  debugInfo?: SendMessageResponse["debug_info"];
  showDebug?: boolean;
}

export const MessageBubble = memo(function MessageBubble({
  role,
  content,
  timestamp,
  isGroupContinuation,
  isStreaming,
  debugInfo,
  showDebug,
}: MessageBubbleProps) {
  if (role === "system") {
    return (
      <div className="flex justify-center my-2">
        <div className="bg-bubble-system text-text-muted text-[13px] px-3 py-1.5 rounded-[var(--radius-sm)] max-w-[85%] text-center">
          {content}
        </div>
      </div>
    );
  }

  const isUser = role === "user";
  const bubbleColor = isUser ? "bg-bubble-out" : "bg-bubble-in";

  // Grouping radius adjustment
  const baseRadius = "var(--radius-lg)";
  const continuationRadius = "var(--radius-sm)";

  const borderRadius = isUser
    ? isGroupContinuation
      ? `${baseRadius} ${continuationRadius} ${baseRadius} ${baseRadius}`
      : `${baseRadius} ${baseRadius} ${baseRadius} ${baseRadius}`
    : isGroupContinuation
      ? `${continuationRadius} ${baseRadius} ${baseRadius} ${baseRadius}`
      : `${baseRadius} ${baseRadius} ${baseRadius} ${baseRadius}`;

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} ${
        isGroupContinuation ? "mt-[2px]" : "mt-2"
      }`}
    >
      <div
        className={`${bubbleColor} text-text text-[15px] leading-[1.35] px-3 py-2 max-w-[78%] md:max-w-[65%] shadow-sm ${isUser ? "whitespace-pre-wrap" : ""}`}
        style={{ borderRadius }}
      >
        {isUser ? (
          content
        ) : (
          <AssistantMarkdown markdown={content} isStreaming={isStreaming} />
        )}

        {/* Debug info footer */}
        {showDebug && debugInfo && !isUser && (
          <div className="mt-2 pt-2 border-t border-black/10 text-[10px] text-text-subtle font-mono">
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              <span>Agent: <span className="font-semibold">{debugInfo.agent}</span></span>
              {debugInfo.reason && <span>Reason: {debugInfo.reason}</span>}
            </div>
            {debugInfo.tools && debugInfo.tools.length > 0 && (
              <div className="mt-1">
                Tools: {debugInfo.tools.join(", ")}
              </div>
            )}
          </div>
        )}

        {timestamp && (
          <span className="block text-[11px] text-text-subtle mt-1 text-right">
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
});
