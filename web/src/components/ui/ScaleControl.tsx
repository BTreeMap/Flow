interface ScaleControlProps {
    value: number | null;
    onPick: (value: number) => void;
    /** Anchor label under the lowest point. */
    lo: string;
    /** Anchor label under the highest point. */
    hi: string;
    /** Number of points; the study's instruments are all 1-5. */
    points?: number;
    label?: string;
}

/**
 * Canonical anchored rating scale (1-N with end labels).
 *
 * Previously hand-rolled twice — once as a local helper in CueStep, once
 * inline in ReflectStep — which let the two drift apart while measuring the
 * same construct. A research instrument that renders differently in two
 * places is a data problem, not just a styling one, so there is exactly one.
 */
export function ScaleControl({
    value,
    onPick,
    lo,
    hi,
    points = 5,
    label,
}: ScaleControlProps) {
    return (
        <div>
            <div className="flex gap-2" role="radiogroup" aria-label={label ?? `${lo} to ${hi}`}>
                {Array.from({ length: points }, (_, i) => i + 1).map((n) => {
                    const selected = value === n;
                    return (
                        <button
                            key={n}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            aria-label={`${n}${n === 1 ? ` — ${lo}` : n === points ? ` — ${hi}` : ""}`}
                            className={`flex-1 min-h-[var(--tap)] rounded-md border text-sm font-medium transition-[background-color,border-color,color] duration-150 ease-[var(--ease-out)] outline-none focus-visible:ring-2 focus-visible:ring-focus ${
                                selected
                                    ? "bg-primary text-on-primary border-primary"
                                    : "bg-surface border-border text-text-muted hover:bg-surface-2 hover:border-text-subtle"
                            }`}
                            onClick={() => onPick(n)}
                        >
                            {n}
                        </button>
                    );
                })}
            </div>
            <div className="mt-1.5 flex justify-between text-xs text-text-subtle">
                <span>{lo}</span>
                <span>{hi}</span>
            </div>
        </div>
    );
}
