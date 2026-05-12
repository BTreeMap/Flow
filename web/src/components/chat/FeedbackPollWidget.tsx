import { useState } from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { getOrMintToken } from "../../auth/token";
import type { FeedbackPollMetadata } from "../../api/types";

interface FeedbackPollWidgetProps {
  readonly metadata: FeedbackPollMetadata;
  readonly projectId: string;
}

export function FeedbackPollWidget({
  metadata,
  projectId,
}: FeedbackPollWidgetProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleVote = async (actionId: string) => {
    if (isSubmitting || metadata.status === "completed") return;
    setIsSubmitting(true);
    try {
      const token = await getOrMintToken("http");
      await fetch(`/api/p/${projectId}/chat/events/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          action_id: actionId,
          notification_id: metadata.notification_id,
          project_id: projectId,
        }),
      });
    } catch (err) {
      console.error(
        "Feedback dispatch failed",
        { projectId, notificationId: metadata.notification_id, actionId },
        err,
      );
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mt-3 flex flex-col gap-2 w-full max-w-sm">
      {metadata.actions.map((action) => {
        const isSelected = metadata.selected_action_id === action.id;
        const isCompleted = metadata.status === "completed";
        return (
          <button
            key={action.id}
            disabled={isCompleted || isSubmitting}
            onClick={() => void handleVote(action.id)}
            className={`flex items-center justify-between w-full text-left px-4 py-3 rounded-xl border transition-all duration-200 ${
              isCompleted
                ? isSelected
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "bg-surface-2 border-transparent text-text-subtle opacity-60 cursor-default"
                : "bg-surface hover:bg-surface-2 border-divider active:scale-[0.98]"
            }`}
          >
            <span className="font-medium text-[15px]">{action.title}</span>
            {isCompleted && isSelected ? (
              <CheckCircle2 className="w-5 h-5 text-primary" />
            ) : (
              !isCompleted && <Circle className="w-5 h-5 text-text-subtle/40" />
            )}
          </button>
        );
      })}
    </div>
  );
}
