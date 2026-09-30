/**
 * The closing rating.
 *
 * The three items are the study's outcome measures, and they used to be
 * labelled with the names the analysis uses for them -- "Perceived fit",
 * "Action clarity", "Willingness to try". Naming a construct to the person
 * being measured invites them to reason about the construct instead of
 * answering the question, so only the questions are shown now.
 */
import { Button, Card, CardContent, SectionHeader } from "../../components";
import { Chip, ScaleControl } from "../../components/ui";
import type { SparkCondition } from "./sparkData";

export interface RatingState {
    fit: number | null;
    clarity: number | null;
    willing: number | null;
}

interface ReflectStepProps {
    condition: SparkCondition;
    rating: RatingState;
    onChange: (next: RatingState) => void;
    onFinish: () => void;
    onGoto: (cond: SparkCondition) => void;
}

const ITEMS: { key: keyof RatingState; question: string }[] = [
    { key: "fit", question: "How well did this Spark fit you?" },
    { key: "clarity", question: "How clear was what to do?" },
    { key: "willing", question: "How willing are you to actually do it?" },
];

export function ReflectStep({ condition, rating, onChange, onFinish, onGoto }: ReflectStepProps) {
    const allRated = ITEMS.every((it) => rating[it.key] !== null);

    return (
        <div className="space-y-4">
            <SectionHeader size="lg" eyebrow="One last thing" title="Before you go" />

            {ITEMS.map(({ key, question }) => (
                <Card key={key}>
                    <CardContent className="space-y-3">
                        <p className="text-sm font-medium text-text">{question}</p>
                        <ScaleControl
                            value={rating[key]}
                            onPick={(n) => onChange({ ...rating, [key]: n })}
                            lo="Low"
                            hi="High"
                            label={question}
                        />
                    </CardContent>
                </Card>
            ))}

            <Button
                variant="primary"
                size="lg"
                className="w-full"
                disabled={!allRated}
                onClick={onFinish}
            >
                Finish
            </Button>

            {/* Quick jump between the options on the home grid. */}
            <div className="flex gap-2 flex-wrap">
                {(["A", "B", "C", "D"] as SparkCondition[])
                    .filter((c) => c !== condition)
                    .map((c) => (
                        <Chip key={c} tone="quiet" onClick={() => onGoto(c)}>
                            Go to {c}
                        </Chip>
                    ))}
            </div>
        </div>
    );
}
