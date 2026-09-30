/** Condition B — five concrete Sparks, one per vibe.
 *
 *  Replaces the old vibe wheel. The wheel asked participants to name a vibe
 *  before they had seen a single Spark, which is a choice most people cannot
 *  make — the labels alone ("Challenge me") do not say what you would actually
 *  be doing. Here every vibe is represented by one randomly drawn Spark from the
 *  curated library, so the choice is made over the intervention itself and the
 *  vibe is whatever the chosen card happens to be.
 */
import type { SparkCard as SparkCardData } from "../../api/types";
import { SectionHeader } from "../../components";
import { FramingChip, framingOf } from "./FramingChip";

interface SparkSamplerProps {
    eyebrow: string;
    title: string;
    subtitle?: string;
    cards: readonly SparkCardData[];
    /** 1-based position within the sampler, for telemetry. */
    onPick: (card: SparkCardData, rank: number) => void;
}

export function SparkSampler({ eyebrow, title, subtitle, cards, onPick }: SparkSamplerProps) {
    return (
        <div className="space-y-4">
            <SectionHeader size="lg" eyebrow={eyebrow} title={title} subtitle={subtitle} />

            <div className="flex flex-col gap-3">
                {cards.map((card, i) => {
                    const f = framingOf(card.frame);
                    return (
                        <button
                            key={`${card.frame}-${card.title}`}
                            type="button"
                            data-testid={`spark-sample-${card.frame}`}
                            className="text-left rounded-lg border border-border bg-surface overflow-hidden transition-[background-color,border-color] duration-200 ease-[var(--ease-out)] hover:bg-surface-2 hover:border-text-subtle outline-none focus-visible:ring-2 focus-visible:ring-focus"
                            onClick={() => onPick(card, i + 1)}
                        >
                            <div className={`h-1.5 w-full ${f.accentBg}`} aria-hidden="true" />
                            <div className="p-5">
                                <FramingChip frame={card.frame} />
                                <div className="display-sm text-[1.125rem] text-text mt-2.5">{card.title}</div>
                                <p className="text-sm text-text-body mt-1.5 leading-relaxed">{card.action}</p>
                                <p className="text-xs text-text-subtle mt-2.5">{card.reward}</p>
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
