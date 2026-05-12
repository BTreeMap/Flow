import { memo } from "react";
import { AssistantMarkdown } from "../chat/AssistantMarkdown";
import { FeedbackPollWidget } from "../chat/FeedbackPollWidget";
import type { FeedbackPollMetadata } from "../../api/types";

const conditionPillClass = {
  A: "bg-blue-100 text-blue-800",
  B: "bg-purple-100 text-purple-800",
  C: "bg-amber-100 text-amber-800",
  D: "bg-emerald-100 text-emerald-800",
} as const;

function isKnownCondition(value: unknown): value is keyof typeof conditionPillClass {
  return typeof value === "string" && value in conditionPillClass;
}

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
  projectId?: string;
  metadata?: FeedbackPollMetadata | Record<string, unknown>;
  timestamp?: string;
  isGroupContinuation?: boolean;
  isStreaming?: boolean;
  debugInfo?: {
    agent?: string;
    condition?: string;
    prompt_args?: Record<string, unknown>;
    tools?: string[];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    tool_calls?: any[];
  };
  showDebug?: boolean;
}

function isFeedbackPollMetadata(
  metadata: FeedbackPollMetadata | Record<string, unknown> | undefined,
): metadata is FeedbackPollMetadata {
  return metadata?.type === "feedback_poll";
}

export const MessageBubble = memo(function MessageBubble({
  role,
  content,
  projectId,
  metadata,
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
          <>
            <AssistantMarkdown markdown={content} isStreaming={isStreaming} />
            {projectId && isFeedbackPollMetadata(metadata) && (
              <FeedbackPollWidget
                metadata={metadata}
                projectId={projectId}
              />
            )}
          </>
        )}
        {timestamp && (
          <span className="block text-[11px] text-text-subtle mt-1 text-right">
            {timestamp}
          </span>
        )}
      </div>

      {showDebug && debugInfo && !isUser && (
        <div className="max-w-[78%] md:max-w-[65%] px-2 py-1.5 mt-1 text-[10px] text-text-subtle font-mono rounded border border-border bg-surface">
          <div className="flex flex-wrap items-center gap-1">
            <span className="opacity-75">Route:</span>
            <span className="font-semibold">{debugInfo.agent ?? "UNKNOWN"}</span>
            {debugInfo.condition && (
              <span
                className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-semibold ${
                  isKnownCondition(debugInfo.condition)
                    ? conditionPillClass[debugInfo.condition]
                    : "bg-muted text-text-subtle"
                }`}
              >
                {debugInfo.condition}
              </span>
            )}
          </div>
          {debugInfo.tools && debugInfo.tools.length > 0 && (
            <div className="opacity-75 mt-1">Tools: {debugInfo.tools.join(", ")}</div>
          )}
          {debugInfo.prompt_args && (
            <details className="mt-1">
              <summary className="cursor-pointer opacity-75">prompt_args</summary>
              <pre className="whitespace-pre-wrap break-all opacity-75 mt-0.5">
                {safeStringify(debugInfo.prompt_args)}
              </pre>
            </details>
          )}
          {debugInfo.tool_calls && debugInfo.tool_calls.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer opacity-75">
                tool calls ({debugInfo.tool_calls.length})
              </summary>
              <ul className="mt-0.5 space-y-1 list-none pl-0">
                {debugInfo.tool_calls.map((tc, i) => (
                  <li
                    key={typeof tc?.run_id === "string" ? tc.run_id : i}
                    className="border-l border-text-subtle pl-1.5"
                  >
                    <span className="font-semibold">
                      {typeof tc?.tool === "string" ? tc.tool : "unknown_tool"}
                    </span>
                    {tc?.args !== undefined && (
                      <pre className="whitespace-pre-wrap break-all opacity-75 mt-0.5">
                        {safeStringify(tc.args)}
                      </pre>
                    )}
                    {typeof tc?.error === "string" && (
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
