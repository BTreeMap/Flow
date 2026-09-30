/**
 * Conditions C and D — intake, then an adapted Spark.
 *
 * The two conditions are one flow parameterised by its step list, not one
 * component threaded with `condition === "C" ? … : …` at six sites. C settles on
 * a single adapted card at the generate step; D gets a ranked list first and a
 * preview after choosing. Everything downstream is identical.
 *
 * Every screen is a tagged step from `adaptiveFlow` and every index is a real
 * position in that list, so condition C no longer has a `previewStep` that
 * collides with its `timerStep`.
 */
import { useMemo, useState } from "react";
import { Alert, Button, SectionHeader } from "../../components";
import { Chip } from "../../components/ui";
import type { SparkCard as SparkCardData } from "../../api/types";
import { AdjustPanel } from "./AdjustPanel";
import { CueStep } from "./CueStep";
import { DurationControl } from "./DurationControl";
import { FeedbackStep } from "./FeedbackStep";
import { FlowProgress } from "./FlowProgress";
import { IntakeStep } from "./IntakeStep";
import { RankedList } from "./RankedList";
import { ReflectStep } from "./ReflectStep";
import { SparkCard } from "./SparkCard";
import { SparkThinking } from "./SparkThinking";
import { SparkTimer } from "./SparkTimer";
import type { AdaptiveCondition, AdaptiveStep } from "./adaptiveFlow";
import { backFrom, buildAdaptiveFlow, indexOfTag, stepAt } from "./adaptiveFlow";
import { CONDITION_COPY } from "./sparkCopy";
import {
    INTAKE_QUESTIONS,
    buildContextFromProfile,
    conditionAccent,
    emptyProfile,
    type IntakeProfile,
    type SparkCondition,
} from "./sparkData";
import { createSparkClientId, type SparkIdentityProvider } from "./sparkResearchIdentity";
import { useSparkEventTracker } from "./sparkTelemetry";
import { assertNever } from "./sparkTimerState";
import { useFlowTail } from "./useFlowTail";
import { useSparkDuration, type SparkDurationControl } from "./useSparkDuration";
import {
    activeCard,
    isBusy,
    offeredCards,
    useSparkRemix,
    type SparkRemixActions,
    type SparkRemixState,
} from "./useSparkRemix";

interface ConditionAdaptiveProps {
    condition: AdaptiveCondition;
    onExit: () => void;
    onGoto: (c: SparkCondition) => void;
    getIdentity: SparkIdentityProvider;
}

export function ConditionAdaptive({
    condition,
    onExit,
    onGoto,
    getIdentity,
}: ConditionAdaptiveProps) {
    const flow = useMemo(() => buildAdaptiveFlow(condition), [condition]);
    const [index, setIndex] = useState(0);
    const [profile, setProfile] = useState<IntakeProfile>(emptyProfile());
    const [flowId] = useState(createSparkClientId);
    const track = useSparkEventTracker({ condition, flowId, getIdentity });
    const { state, actions, timerPolicy } = useSparkRemix({ flowId, getIdentity });
    const duration = useSparkDuration(timerPolicy);
    const tail = useFlowTail(track);

    const copy = CONDITION_COPY[condition];
    const step = stepAt(flow, index);
    const card = activeCard(state);
    const cards = offeredCards(state);
    /** Where the active card lives: D previews its pick, C never had a list. */
    const cardStage: AdaptiveStep["tag"] = condition === "D" ? "preview" : "generate";

    const goToTag = (tag: AdaptiveStep["tag"]): void => {
        const target = indexOfTag(flow, tag);
        if (target >= 0) setIndex(target);
    };

    // `null` here means there is no previous step to return to -- either this is
    // the first one, or it is the generate step, where re-answering the last
    // question would re-fire a paid model call and discard the remix chain.
    const backTarget = backFrom(flow, index);

    const handleIntakeAnswer = (field: keyof IntakeProfile, value: string): void => {
        track({ event_type: "intake_answered", field, value });
        const next = { ...profile, [field]: value };
        setProfile(next);
        if (index < INTAKE_QUESTIONS.length - 1) {
            setIndex(index + 1);
            return;
        }
        // Last question answered: move to the generate step first so the loader
        // is visible while the model call is in flight, then fire the request.
        goToTag("generate");
        const context = buildContextFromProfile(next);
        // No `frame`: the questions state no vibe. C lets the model choose one;
        // D asks for the catalog, one adapted Spark per vibe.
        actions.generate({
            condition,
            context: context || undefined,
            expects: condition === "D" ? "list" : "one",
        });
    };

    const stage = (
        <CardStage
            card={card}
            state={state}
            actions={actions}
            duration={duration}
            onStart={() => {
                goToTag("timer");
            }}
        />
    );

    const body = ((): React.ReactNode => {
        switch (step.tag) {
            case "intake":
                return (
                    <IntakeStep
                        stepIndex={step.index}
                        profile={profile}
                        onAnswer={handleIntakeAnswer}
                    />
                );

            case "generate":
                return (
                    <div className="space-y-4">
                        {(state.tag === "generating" || state.tag === "empty") && (
                            <SparkThinking phrases={copy.thinking} />
                        )}
                        {state.tag === "failed" && (
                            <Alert variant="error" data-testid="spark-error">
                                {state.message}
                            </Alert>
                        )}
                        {condition === "D" && cards.length > 0 && (
                            <RankedList
                                eyebrow={copy.eyebrow}
                                title={copy.title}
                                subtitle={copy.subtitle}
                                cards={cards}
                                onPick={(picked, rank) => {
                                    // Revealed vibe plus rank within the list.
                                    track({ event_type: "frame_selected", frame: picked.frame });
                                    track({ event_type: "card_selected", rank });
                                    actions.selectCard(picked);
                                    goToTag("preview");
                                }}
                            />
                        )}
                        {condition === "C" && card !== null && (
                            <>
                                <SectionHeader
                                    size="lg"
                                    eyebrow={copy.eyebrow}
                                    title={copy.title}
                                    subtitle={copy.subtitle}
                                />
                                {stage}
                            </>
                        )}
                        {state.tag === "failed" && card === null && cards.length === 0 && (
                            <Button size="lg" className="w-full" onClick={actions.retry}>
                                Try again
                            </Button>
                        )}
                    </div>
                );

            case "preview":
                return (
                    <div className="space-y-2">
                        <p className="eyebrow text-text-subtle">Your pick</p>
                        {stage}
                    </div>
                );

            case "timer":
                return card === null ? null : (
                    <SparkTimer
                        frame={card.frame}
                        duration={duration.seconds}
                        onDone={(completion, elapsedMs) => {
                            track({
                                event_type: "timer_finished",
                                completion,
                                duration_seconds: duration.seconds,
                                elapsed_ms: Math.round(elapsedMs),
                                duration_source: duration.source,
                            });
                            goToTag("feedback");
                        }}
                    />
                );

            case "feedback":
                return (
                    <>
                        <FeedbackStep state={tail.feedback} onChange={tail.setFeedback} rich />
                        <div className="flex gap-3 mt-4 flex-wrap">
                            <Chip
                                // Gated exactly like "Next". Tapping this with an
                                // empty form used to send the model the literal
                                // adjustment "different" on the participant's behalf.
                                disabled={
                                    !tail.canSubmitFeedback || tail.feedbackAdjustment === null
                                }
                                onClick={() => {
                                    tail.submitFeedback();
                                    if (tail.feedbackAdjustment !== null) {
                                        actions.adjust(tail.feedbackAdjustment);
                                    }
                                    goToTag(cardStage);
                                }}
                            >
                                ↻ Try another like this
                            </Chip>
                            <Chip
                                disabled={!tail.canSubmitFeedback}
                                onClick={() => {
                                    tail.submitFeedback();
                                    goToTag("cue");
                                }}
                            >
                                Next
                            </Chip>
                        </div>
                    </>
                );

            case "cue":
                return (
                    <>
                        <CueStep
                            profile={profile}
                            cue={tail.cue}
                            confidence={tail.confidence}
                            onCue={tail.setCue}
                            onConfidence={tail.setConfidence}
                        />
                        <Button
                            size="lg"
                            className="w-full mt-5"
                            disabled={tail.cue === null}
                            onClick={() => {
                                tail.submitCue();
                                goToTag("reflect");
                            }}
                        >
                            Next
                        </Button>
                    </>
                );

            case "reflect":
                return (
                    <ReflectStep
                        condition={condition}
                        rating={tail.rating}
                        onChange={tail.setRating}
                        onFinish={() => {
                            tail.submitCompletion();
                            onExit();
                        }}
                        onGoto={onGoto}
                    />
                );

            default:
                return assertNever(step);
        }
    })();

    return (
        <div>
            <FlowProgress
                step={index}
                total={flow.length}
                accent={conditionAccent(condition)}
                onBack={
                    backTarget === null
                        ? null
                        : () => {
                              setIndex(backTarget);
                          }
                }
                onHome={onExit}
            />
            {body}
        </div>
    );
}

/** The card plus everything that acts on it. Identical in C and in D. */
function CardStage({
    card,
    state,
    actions,
    duration,
    onStart,
}: {
    card: SparkCardData | null;
    state: SparkRemixState;
    actions: SparkRemixActions;
    duration: SparkDurationControl;
    onStart: () => void;
}) {
    if (card === null) return null;
    const busy = isBusy(state);
    return (
        <div className="space-y-2">
            <SparkCard
                card={card}
                showWhy
                tuned
                duration={duration.seconds}
                data-testid="spark-card"
            />
            <AdjustPanel
                card={card}
                lastAdjustment={state.tag === "card" ? state.lastAdjustment : null}
                loading={busy}
                onAdjust={actions.adjust}
                onFrameSwitch={actions.switchFrame}
            />
            {state.tag === "failed" && <Alert variant="error">{state.message}</Alert>}
            <div className="mt-5">
                <DurationControl duration={duration} />
            </div>
            <Button size="lg" className="w-full mt-5" disabled={busy} onClick={onStart}>
                Start timer
            </Button>
        </div>
    );
}
