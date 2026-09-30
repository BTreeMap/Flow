import type { SparkCard as SparkCardData } from "../../api/types";
import { FramingChip, framingOf } from "./FramingChip";
import type { SparkDuration } from "./sparkDuration";
import { formatDuration } from "./sparkDuration";

interface SparkCardProps {
    card: SparkCardData;
    /** The countdown this card will be done against, as the participant set it. */
    duration: SparkDuration;
    showWhy?: boolean;
    /** Show a warm "tuned to you" badge (conditions C & D). */
    tuned?: boolean;
    /** Extra className for the outer wrapper */
    className?: string;
    "data-testid"?: string;
}

export function SparkCard({
    card,
    duration,
    showWhy = true,
    tuned = false,
    className = "",
    ...rest
}: SparkCardProps) {
    const f = framingOf(card.frame);

    return (
        <div
            className={`rounded-xl overflow-hidden border border-border bg-surface ${className}`}
            {...rest}
        >
            {/* colored band — the one place a vibe reads as a surface */}
            <div className={`h-1.5 w-full ${f.accentBg}`} aria-hidden="true" />
            <div className="p-6">
                <div className="flex flex-wrap items-center gap-2 mb-3">
                    <FramingChip frame={card.frame} />
                    {tuned && (
                        <span
                            className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1 text-xs font-medium ${f.tintBg} ${f.accentText}`}
                        >
                            <span aria-hidden="true">✨</span> Tuned to your vibe
                        </span>
                    )}
                </div>

                <h3 className="display-sm text-text">
                    {card.title}
                </h3>
                <p className="mt-3 text-base text-text-body leading-relaxed">{card.action}</p>

                {/* meta pills */}
                <div className="flex flex-wrap gap-2 mt-4">
                    <span className="text-xs text-text-muted border border-border rounded-md px-2.5 py-1">
                        ⏱ {formatDuration(duration)}
                    </span>
                    <span className="text-xs text-text-muted border border-border rounded-md px-2.5 py-1">
                        ✓ Done when timer hits 0
                    </span>
                </div>

                {/* reward */}
                <div
                    className={`mt-4 text-sm text-text-body pl-3 border-l-2 py-2 rounded-r-md bg-surface-2 ${f.accentBorder}`}
                >
                    {card.reward}
                </div>

                {/* why (expandable) */}
                {showWhy && card.why && (
                    <details className="mt-4">
                        <summary className={`text-sm font-medium cursor-pointer list-none ${f.accentText}`}>
                            Why this Spark?
                        </summary>
                        <p className="mt-2 text-sm text-text-muted">{card.why}</p>
                    </details>
                )}
            </div>
        </div>
    );
}
