import { memo } from "react";
import { AssistantMarkdown } from "../chat/AssistantMarkdown";

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

interface MessageBubbleProps {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
  isGroupContinuation?: boolean;
  isStreaming?: boolean;
  debugInfo?: {
    agent?: string;
    tools?: string[];
    tool_calls?: Array<{
      tool: string;
      args?: unknown;
      output?: unknown;
      error?: string;
      run_id?: string;
    }>;
  };
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
      className={`flex flex-col ${isUser ? "items-end" : "items-start"} ${
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
        {timestamp && (
          <span className="block text-[11px] text-text-subtle mt-1 text-right">
            {timestamp}
          </span>
        )}
      </div>

      {showDebug && debugInfo && !isUser && (
        <div className="max-w-[78%] md:max-w-[65%] px-1 mt-1 text-[10px] text-text-subtle font-mono">
          <span className="font-semibold">{debugInfo.agent}</span>
          {debugInfo.tools && debugInfo.tools.length > 0 && (
            <span className="opacity-75"> using {debugInfo.tools.join(", ")}</span>
          )}
          {debugInfo.tool_calls && debugInfo.tool_calls.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer opacity-75">
                tool calls ({debugInfo.tool_calls.length})
              </summary>
              <ul className="mt-0.5 space-y-1 list-none pl-0">
                {debugInfo.tool_calls.map((tc, i) => (
                  <li key={tc.run_id ?? i} className="border-l border-text-subtle pl-1.5">
                    <span className="font-semibold">{tc.tool}</span>
                    {tc.args !== undefined && (
                      <pre className="whitespace-pre-wrap break-all opacity-75 mt-0.5">
                        {safeStringify(tc.args)}
                      </pre>
                    )}
                    {tc.error && (
                      <span className="text-red-500 block">error: {tc.error}</span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
});
