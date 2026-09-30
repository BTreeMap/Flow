import { describe, expect, it } from "vitest";
import { backFrom, buildAdaptiveFlow, indexOfTag, stepAt } from "./adaptiveFlow";
import { INTAKE_QUESTIONS } from "./sparkData";

const INTAKE = INTAKE_QUESTIONS.length;

describe("buildAdaptiveFlow", () => {
    it("gives condition C no preview step", () => {
        // C settles on its single adapted card at the generate step. The old
        // arithmetic gave C a previewStep anyway, and it collided with
        // timerStep on the same integer.
        const flow = buildAdaptiveFlow("C");
        expect(indexOfTag(flow, "preview")).toBe(-1);
        expect(flow.map((s) => s.tag)).toEqual([
            ...Array<string>(INTAKE).fill("intake"),
            "generate",
            "timer",
            "feedback",
            "cue",
            "reflect",
        ]);
    });

    it("gives condition D a preview between the list and the timer", () => {
        const flow = buildAdaptiveFlow("D");
        expect(indexOfTag(flow, "preview")).toBe(indexOfTag(flow, "generate") + 1);
        expect(indexOfTag(flow, "timer")).toBe(indexOfTag(flow, "preview") + 1);
    });

    it.each(["C", "D"] as const)("never gives %s two steps the same index", (condition) => {
        const flow = buildAdaptiveFlow(condition);
        const positions = flow.map((_step, i) => i);
        expect(new Set(positions).size).toBe(flow.length);
        // Every non-intake tag appears exactly once.
        const tags = flow.map((s) => s.tag).filter((tag) => tag !== "intake");
        expect(new Set(tags).size).toBe(tags.length);
    });

    it("numbers the intake steps against the question list", () => {
        const flow = buildAdaptiveFlow("C");
        for (let i = 0; i < INTAKE; i++) {
            expect(stepAt(flow, i)).toEqual({ tag: "intake", index: i });
        }
    });

    it("keeps step indices derived from the question list", () => {
        // Adding or removing an intake question must not desynchronise the tail.
        const flow = buildAdaptiveFlow("D");
        expect(indexOfTag(flow, "generate")).toBe(INTAKE);
        expect(flow.length).toBe(INTAKE + 6);
    });
});

describe("stepAt", () => {
    it("is total on an out-of-range index", () => {
        const flow = buildAdaptiveFlow("C");
        expect(stepAt(flow, -5)).toEqual({ tag: "intake", index: 0 });
        expect(stepAt(flow, 999)).toEqual({ tag: "intake", index: 0 });
    });
});

describe("backFrom", () => {
    it("has no previous step from the first step", () => {
        expect(backFrom(buildAdaptiveFlow("C"), 0)).toBeNull();
    });

    it.each(["C", "D"] as const)(
        "offers %s no way back to the last question from generate",
        (condition) => {
            // Re-answering the last intake question re-fires a paid model call
            // and discards the whole remix chain. That is a rejected
            // transition, not navigation.
            const flow = buildAdaptiveFlow(condition);
            expect(backFrom(flow, indexOfTag(flow, "generate"))).toBeNull();
        },
    );

    it("steps back one screen everywhere else", () => {
        const flow = buildAdaptiveFlow("D");
        const timer = indexOfTag(flow, "timer");
        expect(backFrom(flow, timer)).toBe(timer - 1);
        expect(stepAt(flow, timer - 1).tag).toBe("preview");
    });

    it("walks condition C from reflect back to the generate step without landing on a preview", () => {
        const flow = buildAdaptiveFlow("C");
        const seen: string[] = [];
        let index: number | null = indexOfTag(flow, "reflect");
        while (index !== null) {
            seen.push(stepAt(flow, index).tag);
            index = backFrom(flow, index);
        }
        expect(seen).toEqual(["reflect", "cue", "feedback", "timer", "generate"]);
    });
});
