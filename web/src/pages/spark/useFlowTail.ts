/**
 * The shared tail every condition ends with: feedback, cue, rating.
 *
 * All four conditions declared the same seven pieces of state and re-typed the
 * same telemetry calls, which is how the adaptive flow ended up able to submit
 * the *same* feedback twice. Its "adapt from feedback" chip returned to the
 * generate step without clearing the answers, so a second pass through the
 * feedback screen re-emitted the identical payload under a fresh client event
 * id -- two rows, both persisted, double-counted in analysis.
 *
 * Submission is idempotent per distinct answer set: re-submitting answers that
 * have not changed since the last emit is a no-op. Changing one and submitting
 * again is a real event and is sent.
 */
import { useCallback, useRef, useState } from "react";
import type { FeedbackState } from "./FeedbackStep";
import type { RatingState } from "./ReflectStep";
import type { SparkTelemetryEvent } from "./sparkTelemetry";

type Track = (event: SparkTelemetryEvent) => void;

export interface FlowTail {
    readonly feedback: FeedbackState;
    readonly setFeedback: (next: FeedbackState) => void;
    readonly cue: string | null;
    readonly setCue: (next: string) => void;
    readonly confidence: number | null;
    readonly setConfidence: (next: number) => void;
    readonly rating: RatingState;
    readonly setRating: (next: RatingState) => void;
    /** True once the feedback question has an answer; gates every action on it. */
    readonly canSubmitFeedback: boolean;
    /**
     * What the participant asked to change, or `null` when they said nothing.
     *
     * The old code fell back to the literal string "different" and sent it to
     * the model as an adjustment, so tapping "adapt" with an empty form asked
     * for a different Spark on the participant's behalf.
     */
    readonly feedbackAdjustment: string | null;
    readonly submitFeedback: () => void;
    readonly submitCue: () => void;
    readonly submitCompletion: () => void;
}

const emptyFeedback: FeedbackState = { tried: null, reason: null, tweak: "" };
const emptyRating: RatingState = { fit: null, clarity: null, willing: null };

export function useFlowTail(track: Track): FlowTail {
    const [feedback, setFeedback] = useState<FeedbackState>(emptyFeedback);
    const [cue, setCue] = useState<string | null>(null);
    const [confidence, setConfidence] = useState<number | null>(null);
    const [rating, setRating] = useState<RatingState>(emptyRating);

    // Signatures of what has already been reported, so a second submit of the
    // same answers is not a second research row.
    const sentRef = useRef<{ feedback: string | null; cue: string | null }>({
        feedback: null,
        cue: null,
    });

    const tweak = feedback.tweak.trim();
    const feedbackAdjustment = tweak.length > 0 ? tweak : feedback.reason;

    const submitFeedback = useCallback(() => {
        if (feedback.tried === null) return;
        const signature = JSON.stringify([
            feedback.tried,
            feedback.reason,
            feedback.tweak.trim(),
        ]);
        if (sentRef.current.feedback === signature) return;
        sentRef.current.feedback = signature;
        track({
            event_type: "feedback_submitted",
            tried: feedback.tried,
            reason: feedback.reason,
            tweak: feedback.tweak,
        });
    }, [feedback, track]);

    const submitCue = useCallback(() => {
        if (cue === null) return;
        const signature = JSON.stringify([cue, confidence]);
        if (sentRef.current.cue === signature) return;
        sentRef.current.cue = signature;
        track({ event_type: "cue_selected", cue, confidence });
    }, [confidence, cue, track]);

    const submitCompletion = useCallback(() => {
        const { fit, clarity, willing } = rating;
        // Ratings are 1-5, so absence is the only falsy case -- but check it as
        // absence rather than truthiness so a future 0 point on the scale does
        // not silently drop the completion record.
        if (fit === null || clarity === null || willing === null) return;
        track({ event_type: "condition_completed", fit, clarity, willing });
    }, [rating, track]);

    return {
        feedback,
        setFeedback,
        cue,
        setCue,
        confidence,
        setConfidence,
        rating,
        setRating,
        canSubmitFeedback: feedback.tried !== null,
        feedbackAdjustment,
        submitFeedback,
        submitCue,
        submitCompletion,
    };
}
