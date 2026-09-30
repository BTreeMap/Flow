/**
 * Spark — movement micro-coach (research prototype).
 *
 * Four options (A/B/C/D) are reachable from the home grid. Each runs its own
 * step machine; adjustments remix cumulatively on the prior card via
 * useSparkRemix, so the card *evolves* rather than resetting.
 *
 * The flows live in their own modules (ConditionA/ConditionB/ConditionAdaptive)
 * and share the tail — feedback, cue, rating — through useFlowTail. This file is
 * routing only.
 *
 * Visual design: no Spark-local styling exception. Surfaces, type and the five
 * framing accents all resolve through the global token layer, and controls come
 * from the shared primitives. Only keyframe animation lives in spark.css.
 */
import { useState } from "react";
import { PageHeader } from "../components/ui";
import { ConditionA } from "./spark/ConditionA";
import { ConditionAdaptive } from "./spark/ConditionAdaptive";
import { ConditionB } from "./spark/ConditionB";
import { SparkHome } from "./spark/SparkHome";
import { getSparkResearchIdentity } from "./spark/sparkResearchIdentity";
import type { SparkCondition } from "./spark/sparkData";
import "./spark/spark.css";

export function Spark() {
    const [condition, setCondition] = useState<SparkCondition | null>(null);
    const getIdentity = getSparkResearchIdentity;

    function goto(c: SparkCondition | null) {
        setCondition(c);
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    const exit = () => {
        goto(null);
    };
    const jump = (c: SparkCondition) => {
        goto(c);
    };

    return (
        <div className="flex flex-col flex-1 bg-bg">
            <PageHeader title="Spark" data-testid="spark-heading" />
            <div className="px-4 py-6 max-w-3xl mx-auto w-full" data-testid="spark-page">
                {condition === null && <SparkHome onStart={jump} />}
                {condition === "A" && (
                    <ConditionA onExit={exit} onGoto={jump} getIdentity={getIdentity} />
                )}
                {condition === "B" && (
                    <ConditionB onExit={exit} onGoto={jump} getIdentity={getIdentity} />
                )}
                {(condition === "C" || condition === "D") && (
                    <ConditionAdaptive
                        // Remount on a condition switch: each flow owns its own
                        // flow id, remix chain and telemetry, and must not
                        // inherit the previous condition's.
                        key={condition}
                        condition={condition}
                        onExit={exit}
                        onGoto={jump}
                        getIdentity={getIdentity}
                    />
                )}
            </div>
        </div>
    );
}
