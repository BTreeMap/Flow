/**
 * Condition A — one Spark, delivered.
 *
 * No landing step: choosing the option already *is* the request, so a
 * "Get my Spark" tap would ask nothing and would put A out of step with B,
 * which opens straight onto its Sparks. No adjust panel either: the card is
 * delivered as-is.
 */
import { useState } from "react";
import { Alert, Button, SectionHeader } from "../../components";
import { CueStep } from "./CueStep";
import { DurationControl } from "./DurationControl";
import { FeedbackStep } from "./FeedbackStep";
import { ReflectStep } from "./ReflectStep";
import { SparkCard } from "./SparkCard";
import { SparkThinking } from "./SparkThinking";
import { SparkTimer } from "./SparkTimer";
import { FlowProgress } from "./FlowProgress";
import { CONDITION_COPY } from "./sparkCopy";
import { conditionAccent, emptyProfile, type SparkCondition } from "./sparkData";
import { createSparkClientId, type SparkIdentityProvider } from "./sparkResearchIdentity";
import { useSparkEventTracker } from "./sparkTelemetry";
import { useFlowTail } from "./useFlowTail";
import { useSparkDuration } from "./useSparkDuration";
import { activeCard, useSparkRemix } from "./useSparkRemix";

/** A's linear flow, named so a step can move without renumbering every guard. */
const A_STEP = { card: 0, timer: 1, feedback: 2, cue: 3, reflect: 4 } as const;
const A_TOTAL = Object.keys(A_STEP).length;

interface ConditionProps {
    onExit: () => void;
    onGoto: (c: SparkCondition) => void;
    getIdentity: SparkIdentityProvider;
}

export function ConditionA({ onExit, onGoto, getIdentity }: ConditionProps) {
    const [step, setStep] = useState<number>(A_STEP.card);
    const [flowId] = useState(createSparkClientId);
    const track = useSparkEventTracker({ condition: "A", flowId, getIdentity });
    const { state, actions, timerPolicy } = useSparkRemix({
        flowId,
        getIdentity,
        autoGenerate: { condition: "A", expects: "one" },
    });
    const duration = useSparkDuration(timerPolicy);
    const tail = useFlowTail(track);
    const copy = CONDITION_COPY.A;
    const card = activeCard(state);

    return (
        <div>
            <FlowProgress
                step={step}
                total={A_TOTAL}
                accent={conditionAccent("A")}
                onBack={
                    step > 0
                        ? () => {
                              setStep((s) => s - 1);
                          }
                        : null
                }
                onHome={onExit}
            />

            {step === A_STEP.card && (
                <div className="space-y-4">
                    <SectionHeader
                        size="lg"
                        eyebrow={copy.eyebrow}
                        title={copy.title}
                        subtitle={copy.subtitle}
                    />
                    {state.tag === "failed" && (
                        <Alert variant="error" data-testid="spark-error">
                            {state.message}
                        </Alert>
                    )}
                    {card !== null ? (
                        <>
                            <SparkCard card={card} duration={duration.seconds} data-testid="spark-card" />
                            <div className="mt-5">
                                <DurationControl duration={duration} />
                            </div>
                            <Button
                                size="lg"
                                className="w-full mt-5"
                                onClick={() => setStep(A_STEP.timer)}
                            >
                                Start timer
                            </Button>
                        </>
                    ) : state.tag === "generating" ? (
                        <SparkThinking />
                    ) : (
                        <Button size="lg" className="w-full mt-5" onClick={actions.retry}>
                            Try again
                        </Button>
                    )}
                </div>
            )}

            {step === A_STEP.timer && card !== null && (
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
                        setStep(A_STEP.feedback);
                    }}
                />
            )}

            {step === A_STEP.feedback && (
                <>
                    <FeedbackStep state={tail.feedback} onChange={tail.setFeedback} />
                    <Button
                        size="lg"
                        className="w-full mt-5"
                        disabled={!tail.canSubmitFeedback}
                        onClick={() => {
                            tail.submitFeedback();
                            setStep(A_STEP.cue);
                        }}
                    >
                        Next
                    </Button>
                </>
            )}

            {step === A_STEP.cue && (
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
                            setStep(A_STEP.reflect);
                        }}
                    >
                        Next
                    </Button>
                </>
            )}

            {step === A_STEP.reflect && (
                <ReflectStep
                    condition="A"
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
