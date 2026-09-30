/**
 * Condition B — five concrete Sparks, one per vibe, chosen from.
 *
 * Step 0 loads five real Sparks straight away, so the first thing a participant
 * sees is the intervention rather than five adjectives to gamble on. The vibe is
 * revealed by which card they pick, never declared up front. No post-pick
 * remix: the choice happens at the sampler.
 */
import { useState } from "react";
import { Alert, Button } from "../../components";
import { CueStep } from "./CueStep";
import { DurationControl } from "./DurationControl";
import { FeedbackStep } from "./FeedbackStep";
import { ReflectStep } from "./ReflectStep";
import { SparkCard } from "./SparkCard";
import { SparkSampler } from "./SparkSampler";
import { SparkThinking } from "./SparkThinking";
import { SparkTimer } from "./SparkTimer";
import { FlowProgress } from "./FlowProgress";
import { CONDITION_COPY } from "./sparkCopy";
import { conditionAccent, emptyProfile, type SparkCondition } from "./sparkData";
import { createSparkClientId, type SparkIdentityProvider } from "./sparkResearchIdentity";
import { useSparkEventTracker } from "./sparkTelemetry";
import { useFlowTail } from "./useFlowTail";
import { useSparkDuration } from "./useSparkDuration";
import { activeCard, offeredCards, useSparkRemix } from "./useSparkRemix";

/** B's linear flow. Mirrors A with the sampler in front. */
const B_STEP = { sampler: 0, card: 1, timer: 2, feedback: 3, cue: 4, reflect: 5 } as const;
const B_TOTAL = Object.keys(B_STEP).length;

interface ConditionProps {
    onExit: () => void;
    onGoto: (c: SparkCondition) => void;
    getIdentity: SparkIdentityProvider;
}

export function ConditionB({ onExit, onGoto, getIdentity }: ConditionProps) {
    const [step, setStep] = useState<number>(B_STEP.sampler);
    const [flowId] = useState(createSparkClientId);
    const track = useSparkEventTracker({ condition: "B", flowId, getIdentity });
    const { state, actions, timerPolicy } = useSparkRemix({
        flowId,
        getIdentity,
        autoGenerate: { condition: "B", expects: "list" },
    });
    const duration = useSparkDuration(timerPolicy);
    const tail = useFlowTail(track);
    const copy = CONDITION_COPY.B;
    const card = activeCard(state);
    const cards = offeredCards(state);

    return (
        <div>
            <FlowProgress
                step={step}
                total={B_TOTAL}
                accent={conditionAccent("B")}
                onBack={
                    step > 0
                        ? () => {
                              setStep((s) => s - 1);
                          }
                        : null
                }
                onHome={onExit}
            />

            {step === B_STEP.sampler && (
                <div className="space-y-4">
                    {state.tag === "failed" && (
                        <Alert variant="error" data-testid="spark-error">
                            {state.message}
                        </Alert>
                    )}
                    {cards.length > 0 ? (
                        <SparkSampler
                            eyebrow={copy.eyebrow}
                            title={copy.title}
                            subtitle={copy.subtitle}
                            cards={cards}
                            onPick={(picked, rank) => {
                                // The vibe is revealed by the pick, not declared before it.
                                track({ event_type: "frame_selected", frame: picked.frame });
                                track({ event_type: "card_selected", rank });
                                actions.selectCard(picked);
                                setStep(B_STEP.card);
                            }}
                        />
                    ) : state.tag === "generating" ? (
                        <SparkThinking />
                    ) : (
                        <Button size="lg" className="w-full mt-5" onClick={actions.retry}>
                            Try again
                        </Button>
                    )}
                </div>
            )}

            {step === B_STEP.card && card !== null && (
                <div className="space-y-2">
                    <p className="eyebrow text-text-subtle">Your Spark</p>
                    <SparkCard card={card} duration={duration.seconds} data-testid="spark-card" />
                    <div className="mt-5">
                        <DurationControl duration={duration} />
                    </div>
                    <Button size="lg" className="w-full mt-5" onClick={() => setStep(B_STEP.timer)}>
                        Start timer
                    </Button>
                </div>
            )}

            {step === B_STEP.timer && card !== null && (
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
                        setStep(B_STEP.feedback);
                    }}
                />
            )}

            {step === B_STEP.feedback && (
                <>
                    <FeedbackStep state={tail.feedback} onChange={tail.setFeedback} />
                    <Button
                        size="lg"
                        className="w-full mt-5"
                        disabled={!tail.canSubmitFeedback}
                        onClick={() => {
                            tail.submitFeedback();
                            setStep(B_STEP.cue);
                        }}
                    >
                        Next
                    </Button>
                </>
            )}

            {step === B_STEP.cue && (
                <>
                    <CueStep
                        profile={emptyProfile()}
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
                            setStep(B_STEP.reflect);
                        }}
                    >
                        Next
                    </Button>
                </>
            )}

            {step === B_STEP.reflect && (
                <ReflectStep
                    condition="B"
                    rating={tail.rating}
                    onChange={tail.setRating}
                    onFinish={() => {
                        tail.submitCompletion();
                        onExit();
                    }}
                    onGoto={onGoto}
                />
            )}
        </div>
    );
}
