import { FRAMINGS, type FramingDef, type SparkFrame } from "./sparkData";

/**
 * Total lookup from an untrusted frame string to a framing definition.
 *
 * `card.frame` arrives from the API as a plain string, so every consumer used
 * to write `FRAMINGS[card.frame as SparkFrame] ?? FRAMINGS.calm` — a partial
 * index plus an ad-hoc default, repeated in four files and free to disagree.
 * Resolving it once here makes the fallback a single documented decision.
 */
export function framingOf(frame: string | null | undefined): FramingDef {
    return FRAMINGS[frame as SparkFrame] ?? FRAMINGS.calm;
}

interface FramingChipProps {
    frame: string | null | undefined;
    /** Short label ("Calm") instead of the full one ("Calm me"). */
    short?: boolean;
    className?: string;
}

/** The vibe marker: tinted pill carrying the framing's emoji and name. */
export function FramingChip({ frame, short = false, className = "" }: FramingChipProps) {
    const f = framingOf(frame);
    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1 text-xs font-medium ${f.tintBg} ${f.accentText} ${className}`}
        >
            <span aria-hidden="true">{f.emoji}</span> {short ? f.short : f.label}
        </span>
    );
}
