import { useCallback, useEffect, useRef } from "react";
import api from "../../api/client";
import type { SparkCondition, SparkFrame } from "./sparkData";
import type { DurationSource } from "./sparkDuration";
import { createSparkClientId, type SparkIdentityProvider } from "./sparkResearchIdentity";

export type SparkTelemetryEvent =
    | { event_type: "flow_started" }
    | {
          event_type: "intake_answered";
          /** No "frame" — the intake never asks a participant to name a vibe. */
          field: "anchor" | "action";
          value: string;
      }
    /** Revealed vibe: the frame of the card the participant actually chose. */
    | { event_type: "frame_selected"; frame: SparkFrame }
    /** `rank` is the 1-based position in the flat list picked from: B's sampler
     *  or D's ranked catalog. Both offer at most one Spark per vibe. */
    | { event_type: "card_selected"; rank: number }
    /** The countdown is participant-set, so a completion is only interpretable
     *  alongside the length it ran for and who chose that length. */
    | {
          event_type: "timer_finished";
          completion: "completed" | "skipped";
          duration_seconds: number;
          elapsed_ms: number;
          duration_source: DurationSource;
      }
    | {
          event_type: "feedback_submitted";
          tried: number;
          reason: string | null;
          tweak: string;
      }
    /** No `reminder`: Spark never sent one. The cue is the stated intention. */
    | { event_type: "cue_selected"; cue: string; confidence: number | null }
    | { event_type: "condition_completed"; fit: number; clarity: number; willing: number };

interface SparkEventTrackerOptions {
    condition: SparkCondition;
    flowId: string;
    getIdentity: SparkIdentityProvider;
}

/** Send a typed event without ever exposing the pseudonymous identifiers in logs. */
export function useSparkEventTracker({
    condition,
    flowId,
    getIdentity,
}: SparkEventTrackerOptions): (event: SparkTelemetryEvent) => void {
    const track = useCallback(
        (event: SparkTelemetryEvent): void => {
            void (async () => {
                try {
                    const identity = await getIdentity();
                    const { error } = await api.POST("/spark/events", {
                        body: {
                            identity,
                            flow_id: flowId,
                            client_event_id: createSparkClientId(),
                            condition,
                            event,
                        },
                    });
                    if (error) {
                        console.warn("Spark interaction telemetry was not recorded.");
                    }
                } catch {
                    console.warn("Spark interaction telemetry was not recorded.");
                }
            })();
        },
        [condition, flowId, getIdentity],
    );

    // Once per mounted flow. Without the guard StrictMode's development
    // remount emits two flow_started rows under two client event ids, and both
    // persist -- the same class of double-fire the remix hook guards against.
    const started = useRef(false);
    useEffect(() => {
        if (started.current) return;
        started.current = true;
        track({ event_type: "flow_started" });
    }, [track]);

    return track;
}
