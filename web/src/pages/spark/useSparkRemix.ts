/**
 * useSparkRemix — adaptive remix hook.
 *
 * State model
 * -----------
 * One discriminated union, not a bag of `card` / `cards` / `loading` / `error`
 * fields. That product admitted `loading && error && card && cards.length > 0`,
 * and callers reconstructed the states they actually cared about with ad-hoc
 * predicates ("loading and no card and no cards" meant *first generate*). Here
 * those states have names, and rendering is an exhaustive match.
 *
 * Contract sent to /spark/generate
 * ---------------------------------
 *   First generate:  no base_card, adjustment_history = []
 *   Each adjust:     base_card = current card, adjustment_history = accumulated stack
 *
 * The client-carried-history pattern is unchanged: the backend stays stateless
 * and the frontend owns the remix chain. The *card count* is no longer sent --
 * the server derives it from the condition and whether a base card is present.
 *
 * Request discipline
 * ------------------
 * Every call carries a monotonically increasing request id and an AbortSignal.
 * A response whose id is not the newest is dropped, so two rapid adjusts cannot
 * land out of order, and an unmount (jumping conditions mid-flight) cancels the
 * request instead of setting state on a dead component. Requests are fired from
 * event handlers, never from inside a state updater: an updater that performs a
 * POST is invoked twice under StrictMode, which spent two LLM calls and wrote
 * two research rows for one participant action.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import api from "../../api/client";
import type { SparkCard, SparkGenerateResponse } from "../../api/types";
import type { SparkCondition, SparkFrame } from "./sparkData";
import type { TimerPolicy } from "./sparkDuration";
import { parseTimerPolicy } from "./sparkDuration";
import { createSparkClientId, type SparkIdentityProvider } from "./sparkResearchIdentity";

const MAX_HISTORY = 20;
const GENERIC_ERROR = "Spark generation failed";

/** What was generated, and what is being worked on. */
export type SparkRemixState =
    /** Nothing requested yet, and nothing in flight. */
    | { readonly tag: "empty" }
    /** First generate, nothing to show behind it. */
    | { readonly tag: "generating" }
    /** A list to choose from: condition B's sampler or D's ranked catalog. */
    | { readonly tag: "catalog"; readonly cards: readonly SparkCard[] }
    /** One settled card. `from` is the list it was chosen out of, if any. */
    | {
          readonly tag: "card";
          readonly card: SparkCard;
          readonly lastAdjustment: string | null;
          readonly from: readonly SparkCard[];
      }
    /** A remix in flight. The card stays mounted so the page does not blank. */
    | {
          readonly tag: "remixing";
          readonly card: SparkCard;
          readonly adjustment: string;
          readonly from: readonly SparkCard[];
      }
    /** `card` is null when the very first generate failed and nothing can show. */
    | {
          readonly tag: "failed";
          readonly message: string;
          readonly card: SparkCard | null;
          readonly from: readonly SparkCard[];
      };

export interface SparkRemixActions {
    generate: (opts: GenerateOpts) => void;
    adjust: (text: string) => void;
    switchFrame: (frame: SparkFrame) => void;
    selectCard: (card: SparkCard) => void;
    /** Re-run the last generate after a failure. */
    retry: () => void;
}

export interface SparkRemix {
    readonly state: SparkRemixState;
    readonly actions: SparkRemixActions;
    /** Countdown policy from the most recent response; the built-in until then. */
    readonly timerPolicy: TimerPolicy;
}

interface GenerateOpts {
    condition: SparkCondition;
    frame?: SparkFrame | null;
    context?: string;
    /**
     * Whether this request is for a list to choose from or a single card.
     *
     * Stated by the caller rather than inferred from how many cards came back:
     * a condition D catalog in which the model covered only one vibe is still a
     * list of one, not a settled card, and inferring it would silently skip the
     * choice step that defines the condition.
     */
    expects: "one" | "list";
}

interface SparkRemixResearchContext {
    flowId: string;
    getIdentity: SparkIdentityProvider;
    /**
     * Fire this generate exactly once on mount.
     *
     * Conditions A and B both open straight onto their Spark, so a second
     * "fetch it now" tap would ask nothing. Owning the once-only guard here
     * means a caller cannot forget it and double-fire under StrictMode.
     */
    autoGenerate?: GenerateOpts;
}

/** Surface the API's own explanation instead of a blanket failure string.
 *
 *  FastAPI sends `detail` as a string for handled errors and as a list of
 *  objects for validation failures; anything else falls back to the generic
 *  message. The API reports upstream model failures as 424 rather than 502/504
 *  precisely so this function has something to read: Cloudflare replaces origin
 *  5xx bodies with its own error page, which strips `detail`. A 5xx reaching
 *  here therefore means *our* infrastructure failed, not the model.
 */
function describeApiError(error: unknown): string {
    const detail = (error as { detail?: unknown } | null | undefined)?.detail;
    if (typeof detail === "string" && detail.length > 0) return detail;
    if (Array.isArray(detail)) {
        const messages = detail
            .map((item) => (item as { msg?: unknown }).msg)
            .filter((msg): msg is string => typeof msg === "string");
        if (messages.length > 0) return messages.join("; ");
    }
    return GENERIC_ERROR;
}

/** The card currently on screen, if the state has one. Total. */
export function activeCard(state: SparkRemixState): SparkCard | null {
    switch (state.tag) {
        case "empty":
        case "generating":
        case "catalog":
            return null;
        case "card":
        case "remixing":
            return state.card;
        case "failed":
            return state.card;
    }
}

/** The list on offer, if the state has one. Total. */
export function offeredCards(state: SparkRemixState): readonly SparkCard[] {
    switch (state.tag) {
        case "empty":
        case "generating":
            return [];
        case "catalog":
            return state.cards;
        case "card":
        case "remixing":
        case "failed":
            return state.from;
    }
}

/** Is a request in flight? Total, and the only definition of "busy". */
export function isBusy(state: SparkRemixState): boolean {
    return state.tag === "generating" || state.tag === "remixing";
}

export function useSparkRemix(research: SparkRemixResearchContext): SparkRemix {
    const { flowId, getIdentity, autoGenerate } = research;
    const [state, setState] = useState<SparkRemixState>(() =>
        autoGenerate === undefined ? { tag: "empty" } : { tag: "generating" },
    );
    const [timerPolicy, setTimerPolicy] = useState<TimerPolicy>(() =>
        parseTimerPolicy(undefined),
    );

    // Opts from the last generate, reused by adjust/switchFrame/retry.
    const optsRef = useRef<GenerateOpts>({ condition: "A", expects: "one" });
    const historyRef = useRef<readonly string[]>([]);
    // Newest request wins. A resolved response whose id is stale is discarded.
    const requestIdRef = useRef(0);
    const abortRef = useRef<AbortController | null>(null);

    useEffect(
        () => () => {
            abortRef.current?.abort();
        },
        [],
    );

    const callApi = useCallback(
        (
            opts: GenerateOpts,
            baseCard: SparkCard | null,
            history: readonly string[],
            pending: SparkRemixState,
            fallback: { card: SparkCard | null; from: readonly SparkCard[] },
            expects: "one" | "list",
        ) => {
            abortRef.current?.abort();
            const controller = new AbortController();
            abortRef.current = controller;
            const requestId = requestIdRef.current + 1;
            requestIdRef.current = requestId;
            historyRef.current = history;
            setState(pending);

            void (async () => {
                try {
                    const identity = await getIdentity();
                    const { data, error: apiError } = await api.POST("/spark/generate", {
                        signal: controller.signal,
                        body: {
                            identity,
                            flow_id: flowId,
                            client_event_id: createSparkClientId(),
                            condition: opts.condition,
                            frame_preference: opts.frame ?? undefined,
                            context: opts.context ?? undefined,
                            base_card: baseCard ?? undefined,
                            adjustment_history: [...history],
                        },
                    });
                    if (requestIdRef.current !== requestId) return;
                    if (apiError || !data) throw new Error(describeApiError(apiError));

                    const result = data as SparkGenerateResponse;
                    setTimerPolicy(parseTimerPolicy(result.timer));
                    const cards = result.cards ?? [];
                    const first = cards[0];
                    if (first === undefined) {
                        throw new Error(GENERIC_ERROR);
                    }
                    setState(
                        expects === "list"
                            ? { tag: "catalog", cards }
                            : {
                                  tag: "card",
                                  card: first,
                                  lastAdjustment: history[history.length - 1] ?? null,
                                  from: fallback.from,
                              },
                    );
                } catch (err) {
                    if (controller.signal.aborted) return;
                    if (requestIdRef.current !== requestId) return;
                    setState({
                        tag: "failed",
                        message: err instanceof Error ? err.message : GENERIC_ERROR,
                        card: fallback.card,
                        from: fallback.from,
                    });
                }
            })();
        },
        [flowId, getIdentity],
    );

    const generate = useCallback(
        (opts: GenerateOpts) => {
            optsRef.current = opts;
            callApi(
                opts,
                null,
                [],
                { tag: "generating" },
                { card: null, from: [] },
                opts.expects,
            );
        },
        [callApi],
    );

    // Read state through a ref so handlers never have to run inside an updater.
    const stateRef = useRef(state);
    useEffect(() => {
        stateRef.current = state;
    }, [state]);

    const remix = useCallback(
        (text: string, opts: GenerateOpts) => {
            const current = stateRef.current;
            const card = activeCard(current);
            if (card === null) return;
            const from = offeredCards(current);
            const history = [...historyRef.current, text].slice(-MAX_HISTORY);
            // A remix is always a single card, in every condition.
            callApi(
                opts,
                card,
                history,
                { tag: "remixing", card, adjustment: text, from },
                { card, from },
                "one",
            );
        },
        [callApi],
    );

    const adjust = useCallback(
        (text: string) => {
            remix(text, optsRef.current);
        },
        [remix],
    );

    const switchFrame = useCallback(
        (frame: SparkFrame) => {
            optsRef.current = { ...optsRef.current, frame };
            remix(`switch to ${frame} vibe`, optsRef.current);
        },
        [remix],
    );

    const selectCard = useCallback((card: SparkCard) => {
        historyRef.current = [];
        setState((s) => ({
            tag: "card",
            card,
            lastAdjustment: null,
            from: offeredCards(s),
        }));
    }, []);

    const retry = useCallback(() => {
        generate(optsRef.current);
    }, [generate]);

    const autoFired = useRef(false);
    useEffect(() => {
        if (autoGenerate === undefined || autoFired.current) return;
        autoFired.current = true;
        generate(autoGenerate);
        // `autoGenerate` is read once; later identity changes must not refetch.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [generate]);

    return {
        state,
        actions: { generate, adjust, switchFrame, selectCard, retry },
        timerPolicy,
    };
}
