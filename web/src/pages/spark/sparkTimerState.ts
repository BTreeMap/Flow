/**
 * The countdown's pure core: framework-free, clock-free, directly testable.
 *
 * The old timer held `left: number` and `completion: Completion | null` side by
 * side, a product admitting `left = 37, completion = "completed"`. It also
 * counted `setInterval` ticks, so a throttled background tab under-reported the
 * time that actually passed -- which made `completion` weak evidence even at a
 * fixed 60 seconds, and uninterpretable once the length varies.
 *
 * Here elapsed time is always a difference between two readings of a monotonic
 * clock supplied by the caller. The interval is a *display sampler*, not the
 * clock, so dropped or throttled ticks cost smoothness and nothing else.
 */
import type { SparkDuration } from "./sparkDuration";

export type Completion = "completed" | "skipped";

export type TimerState =
    | {
          readonly tag: "running";
          /** Monotonic reading taken when the countdown started. */
          readonly startedAtMs: number;
          /** Most recent monotonic reading; the only thing a tick advances. */
          readonly nowMs: number;
      }
    | {
          readonly tag: "finished";
          readonly completion: Completion;
          readonly elapsedMs: number;
      };

export function startTimer(nowMs: number): TimerState {
    return { tag: "running", startedAtMs: nowMs, nowMs };
}

function elapsedOf(state: TimerState): number {
    switch (state.tag) {
        case "running":
            // A monotonic clock cannot run backwards, but a caller could pass a
            // stale reading; clamping keeps elapsed time a non-negative quantity.
            return Math.max(0, state.nowMs - state.startedAtMs);
        case "finished":
            return state.elapsedMs;
        default:
            return assertNever(state);
    }
}

/** Advance the display clock, completing the run once the full length elapses. */
export function tickTimer(
    state: TimerState,
    nowMs: number,
    duration: SparkDuration,
): TimerState {
    if (state.tag === "finished") return state;
    const advanced: TimerState = { ...state, nowMs };
    const elapsedMs = elapsedOf(advanced);
    return elapsedMs >= duration * 1000
        ? { tag: "finished", completion: "completed", elapsedMs }
        : advanced;
}

/** End the run early. Idempotent: skipping a finished run changes nothing. */
export function skipTimer(state: TimerState, nowMs: number): TimerState {
    if (state.tag === "finished") return state;
    return {
        tag: "finished",
        completion: "skipped",
        elapsedMs: elapsedOf({ ...state, nowMs }),
    };
}

/** Whole seconds still on the clock, clamped into `[0, duration]`. */
export function remainingSeconds(state: TimerState, duration: SparkDuration): number {
    const remaining = duration - elapsedOf(state) / 1000;
    return Math.max(0, Math.min(duration, Math.ceil(remaining)));
}

/** Fraction of the run completed, in `[0, 1]`, for the progress ring. */
export function progressFraction(state: TimerState, duration: SparkDuration): number {
    if (duration <= 0) return 1;
    return Math.max(0, Math.min(1, elapsedOf(state) / (duration * 1000)));
}

export function assertNever(value: never): never {
    throw new TypeError(`unexpected variant: ${String(value)}`);
}
