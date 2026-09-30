/**
 * The step algebra for the adaptive conditions.
 *
 * The flow used to be arithmetic on a bare integer:
 *
 *     const selectStep  = intakeSteps;
 *     const previewStep = selectStep + 1;          // D only
 *     const timerStep   = hasSelection ? previewStep + 1 : selectStep + 1;
 *
 * In condition C that makes `previewStep === timerStep === 4` -- two distinct
 * screens sharing one integer, kept apart only by a `hasSelection &&` guard at
 * the render site. Conditions A and B had already been moved to named step maps
 * for exactly this reason; C and D kept the arithmetic.
 *
 * Here a flow is a list of tagged steps built once from the question list, so a
 * step C does not have simply does not exist in C's flow, and every index is a
 * position in a real array rather than a sum that has to be re-derived.
 */
import { INTAKE_QUESTIONS } from "./sparkData";

export type AdaptiveStep =
    /** One intake question. `index` addresses INTAKE_QUESTIONS. */
    | { readonly tag: "intake"; readonly index: number }
    /** Generating, then showing what came back. In C this is the card itself. */
    | { readonly tag: "generate" }
    /** D only: the card chosen from the ranked list, with its adjust panel. */
    | { readonly tag: "preview" }
    | { readonly tag: "timer" }
    | { readonly tag: "feedback" }
    | { readonly tag: "cue" }
    | { readonly tag: "reflect" };

export type AdaptiveCondition = "C" | "D";

export type AdaptiveFlow = readonly AdaptiveStep[];

/**
 * Build one condition's flow.
 *
 * O(n) in the number of intake questions (3), once per mount.
 */
export function buildAdaptiveFlow(condition: AdaptiveCondition): AdaptiveFlow {
    const intake: AdaptiveStep[] = INTAKE_QUESTIONS.map((_question, index) => ({
        tag: "intake",
        index,
    }));
    // C settles on its single adapted card at the generate step; only D has a
    // list to choose from first, so only D has a preview.
    const selection: AdaptiveStep[] =
        condition === "D" ? [{ tag: "generate" }, { tag: "preview" }] : [{ tag: "generate" }];
    return [
        ...intake,
        ...selection,
        { tag: "timer" },
        { tag: "feedback" },
        { tag: "cue" },
        { tag: "reflect" },
    ];
}

/** Total: an out-of-range index yields the first step rather than `undefined`. */
export function stepAt(flow: AdaptiveFlow, index: number): AdaptiveStep {
    return flow[index] ?? { tag: "intake", index: 0 };
}

/**
 * Position of the first step with this tag.
 *
 * Returns `-1` when the flow has no such step, which is meaningful: asking a
 * condition C flow for its preview is a question with a real negative answer.
 */
export function indexOfTag(flow: AdaptiveFlow, tag: AdaptiveStep["tag"]): number {
    return flow.findIndex((step) => step.tag === tag);
}

/**
 * Where "back" goes.
 *
 * `null` means there is no previous step, and the caller renders its back
 * control disabled -- leaving is a separate, explicit control. The generate
 * step returns `null` on purpose: re-answering the last intake question
 * re-fires a paid model call and discards the whole remix chain, which is a
 * rejected transition rather than navigation.
 */
export function backFrom(flow: AdaptiveFlow, index: number): number | null {
    if (index <= 0) return null;
    return stepAt(flow, index).tag === "generate" ? null : index - 1;
}
