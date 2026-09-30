/**
 * Every string that differs by condition, in one table.
 *
 * Two reasons it lives here rather than inline. First, the copy that varies
 * between arms is the copy most able to leak the study: the previous version
 * told participants which condition they were in, that four of them existed,
 * what the manipulation was ("what changes is who chooses and how much the
 * system personalizes"), and in condition A what the researchers were testing
 * ("tests whether simply delivering a short action is enough"). Kept as a
 * table, that copy is one thing to diff against the protocol.
 *
 * Second, the rule it follows is not obvious from any single line:
 *
 *   The manipulation must be perceivable; the design must not be.
 *
 * "Shaped around your answers" stays -- a participant who cannot perceive
 * personalization is not receiving the C/D treatment. "Condition C" goes.
 * Construct names the analysis uses ("perceived fit"), research vocabulary
 * ("intake"), cross-arm references, and anything describing why a screen is
 * built the way it is all go with it.
 */
import type { SparkCondition } from "./sparkData";

export interface ConditionCopy {
    readonly eyebrow: string;
    readonly title: string;
    readonly subtitle?: string;
    /** Loader lines while a Spark is generated. C and D only. */
    readonly thinking?: readonly string[];
}

export const CONDITION_COPY: Record<SparkCondition, ConditionCopy> = {
    A: {
        eyebrow: "Your Spark",
        title: "A Spark, sent to you",
        subtitle: "Here's one small way to move right now.",
    },
    B: {
        eyebrow: "Your Sparks",
        title: "Which one would you actually do?",
        subtitle: "Five ways to move right now. Pick whichever appeals.",
    },
    C: {
        eyebrow: "Your Spark",
        title: "Here's your Spark",
        subtitle: "Shaped around what you told us.",
        thinking: [
            "Tailoring a Spark just for you…",
            "Folding in what you told us…",
            "Tuning it to your vibe…",
            "Shaping the perfect little move…",
            "Adding a personal touch…",
        ],
    },
    D: {
        eyebrow: "Your Sparks",
        title: "Ranked for your day",
        subtitle:
            "A Spark from each vibe, shaped around what you told us and ordered by how well it looks like it will fit. Pick whichever appeals.",
        thinking: [
            "Lining up your best matches…",
            "Weighing one Spark per vibe…",
            "Weighing what fits your day…",
            "Sorting Sparks by good-fit energy…",
            "Reading between the lines…",
        ],
    },
};
