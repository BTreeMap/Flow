/**
 * Flow progress — step back, leave, and an animated step bar.
 *
 * These used to be one control doing two jobs: it stepped back mid-flow and
 * silently exited to the home grid at step 0. That conflation was a surprise
 * in the adaptive conditions, where backing out of the generate step also
 * exits — pressing "back" dumped the participant on the home grid with no
 * warning, because re-answering the last question would re-fire a paid model
 * call.
 *
 * Split in two, each control says one thing. Back is disabled when there is no
 * previous step, rather than quietly becoming a different action, and leaving
 * is always deliberate.
 */
import { IconButton } from "../../components/ui";

interface FlowProgressProps {
    step: number;
    total: number;
    /** Tailwind background class for the fill, from `conditionAccent`. */
    accent: string;
    /** `null` when there is no previous step; the control renders disabled. */
    onBack: (() => void) | null;
    onHome: () => void;
}

export function FlowProgress({ step, total, accent, onBack, onHome }: FlowProgressProps) {
    const pct = Math.round(((step + 1) / total) * 100);
    return (
        <div className="flex items-center gap-2 mb-6" aria-label={`Step ${step + 1} of ${total}`}>
            <IconButton
                label="Previous step"
                disabled={onBack === null}
                onClick={() => onBack?.()}
                className="shrink-0 border border-border"
            >
                <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                >
                    <path d="m15 18-6-6 6-6" />
                </svg>
            </IconButton>

            <IconButton
                label="Back to the start"
                onClick={onHome}
                className="shrink-0 border border-border"
            >
                <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                >
                    <path d="M3 10.2 12 3l9 7.2V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />
                    <path d="M9 21v-7h6v7" />
                </svg>
            </IconButton>

            <div className="flex-1 ml-1">
                <div className="flex justify-between text-xs text-text-subtle mb-1.5">
                    <span>
                        Step {step + 1} of {total}
                    </span>
                    <span>{pct}%</span>
                </div>
                <div className="h-1 rounded-pill bg-surface-3 overflow-hidden">
                    <div
                        className={`h-full rounded-pill transition-[width] duration-500 ease-[var(--ease-out)] ${accent}`}
                        style={{ width: `${pct}%` }}
                    />
                </div>
            </div>
        </div>
    );
}
