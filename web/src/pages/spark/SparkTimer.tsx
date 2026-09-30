/**
 * SparkTimer — SVG ring countdown over a participant-set duration.
 *
 * All state transitions live in `sparkTimerState`; this component is the shell:
 * it samples the monotonic clock, renders, and hands the finished run back with
 * the elapsed time the research plane needs.
 */
import { useEffect, useRef, useState } from "react";
import { Chip } from "../../components/ui";
import { framingOf } from "./FramingChip";
import type { SparkDuration } from "./sparkDuration";
import { formatDuration } from "./sparkDuration";
import type { SparkFrame } from "./sparkData";
import type { Completion, TimerState } from "./sparkTimerState";
import {
    progressFraction,
    remainingSeconds,
    skipTimer,
    startTimer,
    tickTimer,
} from "./sparkTimerState";

const R = 88;
const CIRC = 2 * Math.PI * R;
/** Display sampling rate. Finer than 1s so the ring moves smoothly; the clock
 *  is read fresh each time, so the rate never affects the measured elapsed time. */
const SAMPLE_MS = 250;
/** Beat on the "done" panel before handing control back. */
const HANDOFF_MS = 1100;

const now = (): number =>
    typeof performance !== "undefined" ? performance.now() : Date.now();

interface SparkTimerProps {
    frame: SparkFrame;
    duration: SparkDuration;
    onDone: (completion: Completion, elapsedMs: number) => void;
}

export function SparkTimer({ frame, duration, onDone }: SparkTimerProps) {
    const [state, setState] = useState<TimerState>(() => startTimer(now()));
    const onDoneRef = useRef(onDone);

    useEffect(() => {
        onDoneRef.current = onDone;
    });

    useEffect(() => {
        if (state.tag === "finished") return;
        const id = window.setInterval(() => {
            // Read the clock here, never inside the updater: a state updater
            // must stay pure, and StrictMode invokes it twice.
            const at = now();
            setState((s) => tickTimer(s, at, duration));
        }, SAMPLE_MS);
        return () => {
            window.clearInterval(id);
        };
    }, [state.tag, duration]);

    const finished = state.tag === "finished" ? state : null;

    useEffect(() => {
        if (finished === null) return;
        const id = window.setTimeout(
            () => onDoneRef.current(finished.completion, finished.elapsedMs),
            HANDOFF_MS,
        );
        return () => {
            window.clearTimeout(id);
        };
    }, [finished]);

    const f = framingOf(frame);

    if (finished !== null) {
        return (
            <div className="text-center py-8">
                <div
                    className={`w-[72px] h-[72px] rounded-full grid place-items-center mx-auto ${f.accentBg}`}
                    aria-hidden="true"
                >
                    <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="#fff"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        width="38"
                        height="38"
                    >
                        <path d="M20 6 9 17l-5-5" />
                    </svg>
                </div>
                <h3 className="display-sm text-text mt-4">
                    {finished.completion === "skipped"
                        ? "Skipped — good call."
                        : "Done — that's your move."}
                </h3>
                <p className="text-text-muted mt-1">
                    Nice. Notice how your body feels right now.
                </p>
            </div>
        );
    }

    const left = remainingSeconds(state, duration);
    const offset = CIRC * progressFraction(state, duration);

    return (
        <div className="text-center py-8">
            <svg
                className="block mx-auto"
                width="200"
                height="200"
                viewBox="0 0 200 200"
                role="img"
                // Static: a label that changed every sample would make screen
                // readers announce the countdown once per tick.
                aria-label={`Countdown, ${formatDuration(duration)}`}
            >
                <circle
                    cx="100"
                    cy="100"
                    r={R}
                    fill="none"
                    stroke="var(--color-divider)"
                    strokeWidth="14"
                />
                <circle
                    cx="100"
                    cy="100"
                    r={R}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="14"
                    strokeLinecap="round"
                    transform="rotate(-90 100 100)"
                    strokeDasharray={CIRC}
                    strokeDashoffset={offset}
                    className={`spark-ring-progress ${f.accentText}`}
                />
                <text
                    x="100"
                    y="112"
                    textAnchor="middle"
                    className="font-display tabular-nums"
                    fill="var(--color-text)"
                    fontSize="48"
                >
                    {left}
                </text>
            </svg>
            <p className="text-sm text-text-muted mt-2">Move until the timer ends.</p>
            <div className="flex justify-center mt-3">
                <Chip
                    tone="quiet"
                    onClick={() => {
                        const at = now();
                        setState((s) => skipTimer(s, at));
                    }}
                >
                    Skip to end
                </Chip>
            </div>
        </div>
    );
}
