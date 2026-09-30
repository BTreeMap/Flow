/** Constants ported from the HTML prototype — single source of truth for the
 *  Spark React implementation. No business logic here, just typed data.
 */

export type SparkFrame = "calm" | "zoomies" | "silly" | "challenge" | "science";

export interface FramingDef {
    key: SparkFrame;
    label: string;
    short: string;
    emoji: string;
    /** Tailwind text/background class for the accent, e.g. "text-frame-calm".
     *  These resolve to `--color-frame-*` theme tokens, so the vibe palette
     *  retheme in one place with everything else — no inline hex, no
     *  `style={{ color: ... }}` escape hatch. */
    accentText: string;
    accentBg: string;
    accentBorder: string;
    tintBg: string;
    desc: string;
    reward: string;
}

export const FRAMINGS: Record<SparkFrame, FramingDef> = {
    calm: {
        key: "calm",
        label: "Calm me",
        short: "Calm",
        emoji: "🌿",
        accentText: "text-frame-calm",
        accentBg: "bg-frame-calm",
        accentBorder: "border-frame-calm",
        tintBg: "bg-frame-calm-tint",
        desc: "Slow it down and release tension.",
        reward: "A slower reset — notice your shoulders drop and your breath even out.",
    },
    zoomies: {
        key: "zoomies",
        label: "Give me zoomies",
        short: "Zoomies",
        emoji: "⚡",
        accentText: "text-frame-zoomies",
        accentBg: "bg-frame-zoomies",
        accentBorder: "border-frame-zoomies",
        tintBg: "bg-frame-zoomies-tint",
        desc: "A quick jolt of energy.",
        reward: "A quick jolt — get the blood moving and shake off the sluggish feeling.",
    },
    silly: {
        key: "silly",
        label: "Make it silly",
        short: "Silly",
        emoji: "🤪",
        accentText: "text-frame-silly",
        accentBg: "bg-frame-silly",
        accentBorder: "border-frame-silly",
        tintBg: "bg-frame-silly-tint",
        desc: "Permission to look a little ridiculous.",
        reward: "Permission to look a little ridiculous. A grin counts as a rep.",
    },
    challenge: {
        key: "challenge",
        label: "Challenge me",
        short: "Challenge",
        emoji: "🔥",
        accentText: "text-frame-challenge",
        accentBg: "bg-frame-challenge",
        accentBorder: "border-frame-challenge",
        tintBg: "bg-frame-challenge-tint",
        desc: "Push the pace and make it count.",
        reward: "Make it count — keep it crisp and see if you hold the pace the whole way.",
    },
    science: {
        key: "science",
        label: "Give me the science",
        short: "Science",
        emoji: "🔬",
        accentText: "text-frame-science",
        accentBg: "bg-frame-science",
        accentBorder: "border-frame-science",
        tintBg: "bg-frame-science-tint",
        desc: "The why behind the move.",
        reward: "Short movement bursts boost circulation and help refocus attention.",
    },
};

export const FRAME_ORDER: SparkFrame[] = [
    "calm",
    "zoomies",
    "silly",
    "challenge",
    "science",
];

export interface AnchorDef {
    k: string;
    label: string;
    cue: string;
}

export const ANCHORS: AnchorDef[] = [
    { k: "coffee", label: "Make coffee or tea", cue: "right after your coffee or tea" },
    { k: "water", label: "Fill a water bottle or cup", cue: "each time you refill your water" },
    { k: "bathroom", label: "Take a bathroom break", cue: "after a bathroom break" },
    { k: "food", label: "Walk to get a meal", cue: "on the way to grab a meal" },
    { k: "work", label: "Start work or class", cue: "as you start work or class" },
    { k: "break", label: "Have a break between meetings", cue: "in the gap between meetings" },
    { k: "email", label: "Check email / Slack / Teams", cue: "before opening your inbox" },
];

/** The four study conditions */
export type SparkCondition = "A" | "B" | "C" | "D";

export interface ConditionDef {
    id: SparkCondition;
    name: string;
    what: string;
    tags: string[];
    /** Tailwind background class for the letter badge. */
    letterBg: string;
}

export const CONDITIONS: ConditionDef[] = [
    {
        id: "A",
        name: "Random Spark",
        what: "You receive one randomly chosen Spark and act on it.",
        tags: ["No choice", "No intake"],
        letterBg: "bg-text-subtle",
    },
    {
        id: "B",
        name: "Spark Wheel",
        what: "You see one Spark from each of the five vibes and pick the one you like.",
        tags: ["Choice", "No intake"],
        letterBg: "bg-frame-challenge",
    },
    {
        id: "C",
        name: "AI-Adapted Spark",
        what: "A short intake, then one Spark adapted to you.",
        tags: ["Intake", "AI adapts"],
        letterBg: "bg-frame-calm",
    },
    {
        id: "D",
        name: "AI-Ranked Choice",
        what: "A short intake, then one Spark per vibe, ranked by predicted fit.",
        tags: ["Intake", "AI ranks", "Choice"],
        letterBg: "bg-frame-science",
    },
];

/** Tailwind accent class for a condition (progress bar, home cards, badges). */
export function conditionAccent(id: SparkCondition): string {
    return CONDITIONS.find((c) => c.id === id)?.letterBg ?? "bg-text";
}

/** Intake question definitions for conditions C & D.
 *
 *  The intake deliberately asks only about *circumstances* — when, what kind of
 *  move, what daily habit to attach it to. It never asks which vibe the
 *  participant wants: nobody can name that before seeing a Spark, and asking
 *  turned a guess into a hard constraint on everything they were then shown.
 *  Vibe is now revealed by which card they pick (`SparkCard.frame`).
 */
export interface IntakeQuestion {
    field: keyof IntakeProfile;
    question: string;
    sub: string;
    options: readonly { label: string; value: string }[];
}

/** Fixed question list — a constant, not a per-render rebuild. */
export const INTAKE_QUESTIONS: readonly IntakeQuestion[] = [
    {
        field: "anchor",
        question: "Which of these do you do every day?",
        sub: "We attach the move to something you already do, so it sticks.",
        options: ANCHORS.map((a) => ({ label: a.label, value: a.k })),
    },
    {
        field: "action",
        question: "Pick a move you'd actually try.",
        sub: "No wrong answer — we can tweak it later.",
        options: [
            { label: "Reach & Roll", value: "reach" },
            { label: "Quick March", value: "march" },
            { label: "Desk Unwind", value: "neck" },
            { label: "Steady Tree", value: "tree" },
            { label: "Calf Lifts", value: "calf" },
            { label: "Shake It Out", value: "shake" },
            { label: "Surprise me", value: "any" },
        ],
    },
];

/** The label a stored answer was chosen by, for one intake question.
 *
 *  Answers are stored as slugs, so the raw value of the move question is
 *  `reach` or `neck`. Those went to the model verbatim as "preferred move:
 *  reach", which is not a move anyone can name -- the label is what the
 *  participant actually read and picked.
 */
function labelFor(field: keyof IntakeProfile, value: string): string | null {
    const question = INTAKE_QUESTIONS.find((q) => q.field === field);
    return question?.options.find((o) => o.value === value)?.label ?? null;
}

/** Build a context string from the intake profile to send to the LLM.
 *
 *  Only answers that bear on the Spark being generated *now* belong here. A
 *  time-of-day preference does not: the participant is doing the move in the
 *  moment, so "time: Morning" described a reminder that nothing ever sent.
 */
export function buildContextFromProfile(profile: IntakeProfile): string {
    const parts: string[] = [];
    if (profile.anchor) {
        const anchor = ANCHORS.find((a) => a.k === profile.anchor);
        if (anchor) parts.push(`anchor: ${anchor.cue}`);
    }
    if (profile.action && profile.action !== "any") {
        parts.push(`preferred move: ${labelFor("action", profile.action) ?? profile.action}`);
    }
    return parts.join("; ");
}

/** Answers to {@link INTAKE_QUESTIONS}. No `frame`: the intake cannot state a
 *  vibe, so "profile claims a vibe the participant never saw" is unrepresentable. */
export interface IntakeProfile {
    anchor: string | null;
    action: string | null;
}

export function emptyProfile(): IntakeProfile {
    return { anchor: null, action: null };
}

/** Condition D's catalog: one adapted Spark per vibe, ranked against each other.
 *  This is the count requested; the server de-duplicates vibes and serves a
 *  shorter catalog rather than failing when the model returns fewer. */
export const D_CATALOG_SIZE = FRAME_ORDER.length;
