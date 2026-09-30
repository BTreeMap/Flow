/**
 * SparkThinking — playful "the coach is thinking" loader.
 *
 * The LLM can take a few seconds; instead of a cold spinner we keep the user
 * in the playful vibe with a bobbing frame orb, bouncing dots, and a rotating
 * set of witty status lines (à la Claude Code). All motion is gated behind
 * prefers-reduced-motion; reduced-motion users see a single steady line.
 */
import { useEffect, useMemo, useState } from "react";
import { framingOf } from "./FramingChip";
import type { SparkFrame } from "./sparkData";

const PHRASES = [
    "Warming up your Spark…",
    "Doing a few mental jumping jacks…",
    "Shaking out the cobwebs…",
    "Consulting the wiggle department…",
    "Stretching some fresh ideas…",
    "Finding your vibe…",
    "Picking something delightfully doable…",
    "Charging up the good kind of energy…",
    "Rummaging for the perfect little move…",
    "Loosening up the creative hamstrings…",
];

function shuffled(n: number): number[] {
    const order = Array.from({ length: n }, (_, i) => i);
    for (let i = order.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const a = order[i] ?? i;
        const b = order[j] ?? j;
        order[i] = b;
        order[j] = a;
    }
    return order;
}

interface SparkThinkingProps {
    frame?: SparkFrame;
    /** Override the rotating phrases. */
    phrases?: readonly string[];
    /** Compact inline variant (no orb) for use under an existing card. */
    compact?: boolean;
    className?: string;
}

export function SparkThinking({
    frame,
    phrases = PHRASES,
    compact = false,
    className = "",
}: SparkThinkingProps) {
    const f = framingOf(frame);
    const order = useMemo(() => shuffled(phrases.length), [phrases.length]);
    const [tick, setTick] = useState(0);

    useEffect(() => {
        const reduce =
            typeof window !== "undefined" &&
            window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        if (reduce) return;
        const id = window.setInterval(() => {
            setTick((n) => n + 1);
        }, 2100);
        return () => {
            window.clearInterval(id);
        };
    }, [phrases.length]);

    const phraseIndex = order[tick % order.length] ?? 0;
    const phrase = phrases[phraseIndex] ?? "Thinking…";

    return (
        <div
            className={`spark-thinking flex flex-col items-center text-center ${compact ? "py-3 gap-2" : "py-10 gap-4"} ${f.accentText} ${className}`}
        >
            {!compact && (
                <div
                    className={`spark-thinking-orb w-16 h-16 rounded-full grid place-items-center text-2xl ${f.tintBg}`}
                    aria-hidden="true"
                >
                    <span className="spark-thinking-emoji">{f.emoji}</span>
                </div>
            )}
            <div className="spark-thinking-dots" aria-hidden="true">
                <span />
                <span />
                <span />
            </div>
            <p className="spark-thinking-phrase text-sm text-text-muted" key={tick}>
                {phrase}
            </p>
            <p className="sr-only" role="status" aria-live="polite">
                Generating your Spark
            </p>
        </div>
    );
}
