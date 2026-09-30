/** Intake step — one question at a time for conditions C & D */
import { Card, CardContent } from "../../components";
import { ChipGroup } from "../../components/ui";
import type { IntakeProfile } from "./sparkData";
import { INTAKE_QUESTIONS } from "./sparkData";

interface IntakeStepProps {
    stepIndex: number; // 0 … INTAKE_QUESTIONS.length - 1
    profile: IntakeProfile;
    onAnswer: (field: keyof IntakeProfile, value: string) => void;
}

export function IntakeStep({ stepIndex, profile, onAnswer }: IntakeStepProps) {
    const q = INTAKE_QUESTIONS[stepIndex];
    if (!q) return null;

    return (
        <div className="space-y-4">
            <p className="eyebrow text-text-subtle">
                Question {stepIndex + 1} of {INTAKE_QUESTIONS.length}
            </p>

            <Card>
                <CardContent>
                    {/* AI avatar row on first question */}
                    {stepIndex === 0 && (
                        <div className="flex gap-3 mb-5">
                            <div
                                className="flex-none w-9 h-9 rounded-md grid place-items-center bg-primary text-on-primary text-xs font-medium"
                                aria-hidden="true"
                            >
                                AI
                            </div>
                            <p className="text-sm text-text-muted self-center">
                                I'm your micro-coach. Let's find a tiny way to move that fits your day.
                            </p>
                        </div>
                    )}

                    <p className="display-sm text-[1.125rem] text-text">{q.question}</p>
                    <p className="text-sm text-text-muted mt-1 mb-4">{q.sub}</p>

                    <ChipGroup
                        layout="stack"
                        options={q.options.map((opt) => ({ value: opt.value, label: opt.label }))}
                        value={profile[q.field]}
                        onSelect={(value) => onAnswer(q.field, value)}
                    />
                </CardContent>
            </Card>
        </div>
    );
}
