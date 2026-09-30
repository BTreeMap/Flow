/** Condition D — the ranked catalog: one adapted Spark per vibe.
 *
 *  Same choice set as condition B's sampler, so the two differ only in that
 *  these are adapted and ranked against each other. Renders whatever the
 *  catalog contains: a vibe the model failed to supply is simply absent, never
 *  an error. The participant browses concrete Sparks instead of committing to a
 *  vibe label first; whichever card they pick is what reveals the preferred vibe.
 *
 *  Match strength is shown only when the model actually scored the card. The
 *  previous version invented one -- `96 - rank * 7`, floored at 70 -- and
 *  rendered it as "89% match" beside a filled bar. In a study measuring
 *  perceived fit and perceived personalization, a fabricated confidence number
 *  is a number the participant then rates us on. Rank order communicates the
 *  ranking on its own.
 */
import type { SparkCard as SparkCardData } from "../../api/types";
import { SectionHeader } from "../../components";
import { FramingChip, framingOf } from "./FramingChip";

interface RankedListProps {
    eyebrow: string;
    title: string;
    subtitle?: string;
    cards: readonly SparkCardData[];
    /** `rank` is the 1-based position in this list. */
    onPick: (card: SparkCardData, rank: number) => void;
}

/** A score the model actually produced, or absence. No invented middle ground. */
type MatchStrength = { readonly tag: "scored"; readonly pct: number } | { readonly tag: "unscored" };

function matchOf(score: number | null | undefined): MatchStrength {
    return typeof score === "number" && score > 0
        ? { tag: "scored", pct: Math.max(0, Math.min(100, Math.round(score))) }
        : { tag: "unscored" };
}

function matchLabel(pct: number): string {
    if (pct >= 90) return "Top match";
    if (pct >= 80) return "Great fit";
    if (pct >= 73) return "Good fit";
    return "Worth a try";
}

export function RankedList({ eyebrow, title, subtitle, cards, onPick }: RankedListProps) {
    return (
        <div className="space-y-4">
            <SectionHeader size="lg" eyebrow={eyebrow} title={title} subtitle={subtitle} />

            <div className="flex flex-col gap-3">
                {cards.map((card, idx) => {
                    const f = framingOf(card.frame);
                    const match = matchOf(card.fit_score);
                    return (
                        <button
                            key={`${card.title}-${idx}`}
                            type="button"
                            data-testid={`spark-ranked-${card.frame}`}
                            className="text-left rounded-lg border border-border bg-surface shadow-sm p-4 flex gap-3 transition-[transform,border-color] hover:-translate-y-0.5 hover:border-text-subtle"
                            onClick={() => onPick(card, idx + 1)}
                        >
                            {/* rank badge */}
                            <div
                                className={`flex-none w-7 h-7 rounded-md grid place-items-center text-on-primary font-medium text-sm ${f.accentBg}`}
                                aria-label={`Rank ${idx + 1}`}
                            >
                                {idx + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex flex-wrap items-baseline gap-2">
                                    <span className="font-medium text-text">{card.title}</span>
                                    <FramingChip frame={card.frame} short />
                                </div>
                                <p className="text-sm text-text-muted mt-0.5 line-clamp-2">
                                    {card.action}
                                </p>
                                {match.tag === "scored" && (
                                    <>
                                        <div className="mt-2 h-1 rounded-pill bg-surface-3 overflow-hidden">
                                            <div
                                                className={`h-full rounded-pill transition-[width] duration-500 ease-[var(--ease-out)] ${f.accentBg}`}
                                                style={{ width: `${match.pct}%` }}
                                            />
                                        </div>
                                        <p className={`text-xs mt-1 font-medium ${f.accentText}`}>
                                            {idx === 0 ? "✨ " : ""}
                                            {matchLabel(match.pct)} · {match.pct}% match
                                        </p>
                                    </>
                                )}
                                {card.why && (
                                    <p className="text-xs text-text-muted mt-0.5">{card.why}</p>
                                )}
                            </div>
                        </button>
                    );
                })}
            </div>

            <p className="text-xs text-text-muted border border-dashed border-border rounded-xl p-3">
                Each card shows how strong a match it looks like, and why.
            </p>
        </div>
    );
}
