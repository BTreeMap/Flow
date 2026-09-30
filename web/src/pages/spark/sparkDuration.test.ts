import { describe, expect, it } from "vitest";
import {
    FALLBACK_DEFAULT_SECONDS,
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    formatDuration,
    parseDuration,
    parseTimerPolicy,
    resolveDuration,
    type SparkDuration,
} from "./sparkDuration";

/** Test-local constructor: every value here is checked by parseDuration first. */
function duration(seconds: number): SparkDuration {
    const parsed = parseDuration(seconds);
    if (parsed === null) throw new Error(`not a duration: ${seconds}`);
    return parsed;
}

describe("parseDuration", () => {
    it.each([MIN_DURATION_SECONDS, 60, MAX_DURATION_SECONDS])(
        "admits %i seconds",
        (seconds) => {
            expect(parseDuration(seconds)).toBe(seconds);
        },
    );

    it.each([
        ["below the minimum", MIN_DURATION_SECONDS - 1],
        ["above the maximum", MAX_DURATION_SECONDS + 1],
        ["zero", 0],
        ["negative", -60],
        ["fractional", 60.5],
        ["a numeric string", "60"],
        ["null", null],
        ["undefined", undefined],
        ["NaN", Number.NaN],
        ["Infinity", Number.POSITIVE_INFINITY],
    ])("rejects %s", (_label, raw) => {
        expect(parseDuration(raw)).toBeNull();
    });
});

describe("resolveDuration", () => {
    it("falls back to the study default when nothing was chosen", () => {
        expect(resolveDuration(duration(60), null)).toEqual({
            seconds: 60,
            source: "study_default",
        });
    });

    it("prefers an explicit participant choice", () => {
        expect(resolveDuration(duration(60), duration(180))).toEqual({
            seconds: 180,
            source: "participant",
        });
    });

    it("attributes a choice that happens to equal the default", () => {
        // Source records who chose, not whether the number differs: a
        // participant who deliberately picks 60 is not the same research row as
        // one who never touched the control.
        expect(resolveDuration(duration(60), duration(60)).source).toBe("participant");
    });
});

describe("parseTimerPolicy", () => {
    it("uses the built-in fallback when the server sent nothing", () => {
        const policy = parseTimerPolicy(undefined);
        expect(policy.defaultSeconds).toBe(FALLBACK_DEFAULT_SECONDS);
        expect(policy.choices.length).toBeGreaterThan(0);
    });

    it("keeps the served policy when it is in domain", () => {
        const policy = parseTimerPolicy({ default_seconds: 90, choices: [30, 90, 300] });
        expect(policy.defaultSeconds).toBe(90);
        expect(policy.choices).toEqual([30, 90, 300]);
    });

    it("drops out-of-domain choices rather than clamping them", () => {
        // Clamping would silently offer a length the study never sanctioned.
        const policy = parseTimerPolicy({ default_seconds: 60, choices: [5, 60, 9000] });
        expect(policy.choices).toEqual([60]);
    });

    it("still offers the default when every choice was rejected", () => {
        const policy = parseTimerPolicy({ default_seconds: 60, choices: [1, 2, 3] });
        expect(policy.choices).toEqual([60]);
    });

    it("survives a malformed payload", () => {
        const policy = parseTimerPolicy({ default_seconds: "long", choices: "all of them" });
        expect(policy.defaultSeconds).toBe(FALLBACK_DEFAULT_SECONDS);
        expect(policy.choices.length).toBeGreaterThan(0);
    });
});

describe("formatDuration", () => {
    it.each([
        [30, "30 seconds"],
        [60, "1 minute"],
        [90, "90 seconds"],
        [120, "2 minutes"],
        [300, "5 minutes"],
    ])("renders %i as %s", (seconds, expected) => {
        expect(formatDuration(duration(seconds))).toBe(expected);
    });
});
