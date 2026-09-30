import { describe, expect, it } from "vitest";
import { parseDuration, type SparkDuration } from "./sparkDuration";
import {
    progressFraction,
    remainingSeconds,
    skipTimer,
    startTimer,
    tickTimer,
} from "./sparkTimerState";

function duration(seconds: number): SparkDuration {
    const parsed = parseDuration(seconds);
    if (parsed === null) throw new Error(`not a duration: ${seconds}`);
    return parsed;
}

const SIXTY = duration(60);

describe("tickTimer", () => {
    it("advances the display clock while time remains", () => {
        const state = tickTimer(startTimer(1_000), 31_000, SIXTY);
        expect(state.tag).toBe("running");
        expect(remainingSeconds(state, SIXTY)).toBe(30);
    });

    it("completes once the full length has elapsed", () => {
        const state = tickTimer(startTimer(1_000), 61_000, SIXTY);
        expect(state).toEqual({ tag: "finished", completion: "completed", elapsedMs: 60_000 });
    });

    it("reports the real elapsed time when ticks were missed", () => {
        // The whole point of reading a monotonic clock instead of counting
        // ticks: a throttled background tab delivers one late tick, and the run
        // must be reported as the time that actually passed.
        const state = tickTimer(startTimer(0), 240_000, SIXTY);
        expect(state).toEqual({ tag: "finished", completion: "completed", elapsedMs: 240_000 });
    });

    it("is idempotent once finished", () => {
        const finished = tickTimer(startTimer(0), 60_000, SIXTY);
        expect(tickTimer(finished, 120_000, SIXTY)).toBe(finished);
    });

    it("never reports negative elapsed time from a stale reading", () => {
        const state = tickTimer(startTimer(5_000), 1_000, SIXTY);
        expect(remainingSeconds(state, SIXTY)).toBe(60);
    });
});

describe("skipTimer", () => {
    it("ends the run early and keeps the elapsed time", () => {
        expect(skipTimer(startTimer(1_000), 5_200)).toEqual({
            tag: "finished",
            completion: "skipped",
            elapsedMs: 4_200,
        });
    });

    it("cannot overwrite a completed run", () => {
        // A skip tap landing in the same frame as completion must not turn a
        // finished run into a skipped one.
        const finished = tickTimer(startTimer(0), 60_000, SIXTY);
        expect(skipTimer(finished, 60_010)).toBe(finished);
    });
});

describe("remainingSeconds", () => {
    it.each([
        [0, 60],
        [500, 60],
        [1_000, 59],
        [59_500, 1],
        [60_000, 0],
        [999_000, 0],
    ])("reads %ims elapsed as %is left", (elapsed, expected) => {
        expect(remainingSeconds(tickTimer(startTimer(0), elapsed, duration(300)), SIXTY)).toBe(
            expected,
        );
    });

    it("tracks a longer participant-set duration", () => {
        const threeMinutes = duration(180);
        const state = tickTimer(startTimer(0), 60_000, threeMinutes);
        expect(state.tag).toBe("running");
        expect(remainingSeconds(state, threeMinutes)).toBe(120);
    });
});

describe("progressFraction", () => {
    it("stays within [0, 1]", () => {
        const state = tickTimer(startTimer(0), 500_000, duration(300));
        expect(progressFraction(state, duration(300))).toBe(1);
        expect(progressFraction(startTimer(0), SIXTY)).toBe(0);
    });

    it("is half way at half the duration", () => {
        expect(progressFraction(tickTimer(startTimer(0), 30_000, SIXTY), SIXTY)).toBeCloseTo(0.5);
    });
});
