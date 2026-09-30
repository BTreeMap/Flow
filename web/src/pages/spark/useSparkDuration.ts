/**
 * The countdown length a participant has chosen, and where it is remembered.
 *
 * Persisting the pick is what keeps a configurable duration from becoming a
 * choice task repeated on every flow: the participant decides once, and every
 * later Spark starts from that. Storage can be unavailable (private browsing,
 * blocked site data), which is an ordinary outcome, not an error -- the flow
 * simply runs at the study default.
 */
import { useCallback, useState } from "react";
import type { DurationSource, SparkDuration, TimerPolicy } from "./sparkDuration";
import { parseDuration, resolveDuration } from "./sparkDuration";

const DURATION_KEY = "flow.spark.timer-duration.v1";

function readStoredChoice(): SparkDuration | null {
    try {
        const stored = window.localStorage.getItem(DURATION_KEY);
        if (stored === null) return null;
        // Untrusted: another tab, an older build, or a hand-edited value. It
        // crosses the same smart constructor as everything else.
        return parseDuration(Number.parseInt(stored, 10));
    } catch {
        return null;
    }
}

function writeStoredChoice(duration: SparkDuration): void {
    try {
        window.localStorage.setItem(DURATION_KEY, String(duration));
    } catch {
        // A choice that cannot be remembered still applies to this flow.
    }
}

export interface SparkDurationControl {
    /** The length the countdown will run for. */
    readonly seconds: SparkDuration;
    /** Who chose it, for the research record. */
    readonly source: DurationSource;
    readonly choices: readonly SparkDuration[];
    readonly choose: (duration: SparkDuration) => void;
}

/**
 * Resolve the duration in force from the served policy and the stored pick.
 *
 * The stored choice is read once on mount rather than on every render: it is
 * external state this hook owns, and re-reading it would let another tab's
 * write change the length of a countdown already running.
 */
export function useSparkDuration(policy: TimerPolicy): SparkDurationControl {
    const [choice, setChoice] = useState<SparkDuration | null>(readStoredChoice);

    const choose = useCallback((duration: SparkDuration) => {
        setChoice(duration);
        writeStoredChoice(duration);
    }, []);

    const resolved = resolveDuration(policy.defaultSeconds, choice);

    return {
        seconds: resolved.seconds,
        source: resolved.source,
        // A remembered pick outside the served policy still has to be offered,
        // or the control would render with nothing selected.
        choices: policy.choices.includes(resolved.seconds)
            ? policy.choices
            : [...policy.choices, resolved.seconds].sort((a, b) => a - b),
        choose,
    };
}
