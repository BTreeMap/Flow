/**
 * The Spark countdown duration domain.
 *
 * The countdown used to be the literal `60` in SparkTimer plus the phrase "one
 * minute" repeated through card copy, button labels, the static library and the
 * system prompt. Now that a participant sets it, exactly one thing may name a
 * duration -- the resolved value -- and everything else asks {@link formatDuration}.
 *
 * Mirrors `api/app/services/spark_duration.py`. The bounds live in both places
 * because the server cannot trust the browser and the browser cannot wait for
 * the server to reject a chip tap; the wire policy is what reconciles them.
 */

declare const durationBrand: unique symbol;

/** Whole seconds within the study bounds. Construct via {@link parseDuration}. */
export type SparkDuration = number & { readonly [durationBrand]: true };

/**
 * Who chose the duration. Closed, and deliberately without a "the model chose
 * it" variant: nothing populates one today, and a dead variant is a state the
 * analysis has to defend against for no benefit.
 */
export type DurationSource = "study_default" | "participant";

export interface ResolvedDuration {
    readonly seconds: SparkDuration;
    readonly source: DurationSource;
}

export const MIN_DURATION_SECONDS = 15;
export const MAX_DURATION_SECONDS = 300;

/** Used only until the first generate response carries the real policy. */
export const FALLBACK_DEFAULT_SECONDS = 60;
const FALLBACK_CHOICES = [30, 60, 90, 120, 180, 300];

/** What the participant may pick from, as served by the API. */
export interface TimerPolicy {
    readonly defaultSeconds: SparkDuration;
    readonly choices: readonly SparkDuration[];
}

/**
 * Admit an untrusted value, or `null` when it is not a duration.
 *
 * The one place a duration brand is asserted. Callers never cast.
 */
export function parseDuration(raw: unknown): SparkDuration | null {
    if (typeof raw !== "number" || !Number.isInteger(raw)) return null;
    if (raw < MIN_DURATION_SECONDS || raw > MAX_DURATION_SECONDS) return null;
    return raw as SparkDuration;
}

/** Parse a duration, falling back to the study default when it is unusable. */
export function parseDurationOr(raw: unknown, fallback: SparkDuration): SparkDuration {
    return parseDuration(raw) ?? fallback;
}

// Safe by construction: FALLBACK_DEFAULT_SECONDS is a literal inside the bounds
// declared directly above it, so parseDuration cannot reject it. The assertion
// removes the null, not the domain check.
// eslint-disable-next-line @typescript-eslint/no-non-null-assertion
const FALLBACK_DEFAULT = parseDuration(FALLBACK_DEFAULT_SECONDS)!;

/**
 * Parse the timer policy off a generate response.
 *
 * Total: a missing, malformed, or entirely out-of-range policy yields the
 * built-in fallback rather than an exception, because a countdown the
 * participant cannot start is a worse failure than a countdown of the wrong
 * length. Out-of-domain individual choices are dropped, not clamped -- clamping
 * would silently offer a length the study never sanctioned.
 */
export function parseTimerPolicy(raw: unknown): TimerPolicy {
    const source = (raw ?? {}) as { default_seconds?: unknown; choices?: unknown };
    const defaultSeconds = parseDurationOr(source.default_seconds, FALLBACK_DEFAULT);
    const rawChoices = Array.isArray(source.choices) ? source.choices : FALLBACK_CHOICES;
    const choices = rawChoices
        .map(parseDuration)
        .filter((d): d is SparkDuration => d !== null);
    return {
        defaultSeconds,
        // A policy whose every choice was rejected still has to offer the
        // default, or the control renders empty and nothing can be started.
        choices: choices.length > 0 ? choices : [defaultSeconds],
    };
}

/** Total: an explicit participant pick wins, otherwise the study default. */
export function resolveDuration(
    studyDefault: SparkDuration,
    participantChoice: SparkDuration | null,
): ResolvedDuration {
    return participantChoice === null
        ? { seconds: studyDefault, source: "study_default" }
        : { seconds: participantChoice, source: "participant" };
}

/**
 * Human-readable length. Whole minutes read as minutes, everything else as
 * seconds -- "90 seconds" is clearer than "1.5 minutes".
 */
export function formatDuration(seconds: SparkDuration): string {
    if (seconds % 60 !== 0) return `${seconds} seconds`;
    const minutes = seconds / 60;
    return minutes === 1 ? "1 minute" : `${minutes} minutes`;
}
