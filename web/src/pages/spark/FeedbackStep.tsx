import { useState } from "react";
import { Card, CardContent, SectionHeader } from "../../components";
import { ChipGroup } from "../../components/ui";
import { VoiceControl } from "./VoiceControl";

export interface FeedbackState {
    tried: number | null; // 0=Yes, 1=Partly, 2=Not now
    reason: string | null;
    tweak: string;
}

interface FeedbackStepProps {
    state: FeedbackState;
    onChange: (next: FeedbackState) => void;
    /** If true, shows richer explanation that feedback drives adaptation */
    rich?: boolean;
}

const TRIED_OPTIONS = ["Yes, did it", "Partly", "Not now"].map((label, value) => ({
    value,
    label,
}));
const YES_REASONS = ["Easy to start", "Felt good", "Fit the moment", "Liked the vibe"];
const NO_REASONS = ["No time", "Felt awkward", "Wrong moment", "Didn't fit me"];

const asOptions = (labels: readonly string[]) => labels.map((label) => ({ value: label, label }));

export function FeedbackStep({ state, onChange, rich = false }: FeedbackStepProps) {
    const [tweakSaved, setTweakSaved] = useState(false);

    return (
        <div className="space-y-4">
            <SectionHeader size="lg" eyebrow="Quick feedback" title="How did that go?" />

            <Card>
                <CardContent className="space-y-3">
                    <p className="text-sm font-medium text-text">Did you get a chance to try it?</p>
                    <ChipGroup
                        options={TRIED_OPTIONS}
                        value={state.tried}
                        onSelect={(tried) => onChange({ ...state, tried, reason: null })}
                    />
                </CardContent>
            </Card>

            {/* Reason (follow-up) */}
            {state.tried !== null && (
                <Card>
                    <CardContent className="space-y-3">
                        <p className="text-sm font-medium text-text">
                            {state.tried === 0 ? "What made it work?" : "What got in the way?"}
                        </p>
                        <ChipGroup
                            options={asOptions(state.tried === 0 ? YES_REASONS : NO_REASONS)}
                            value={state.reason}
                            onSelect={(reason) => onChange({ ...state, reason })}
                        />
                    </CardContent>
                </Card>
            )}

            {/* Tweak / voice */}
            <Card>
                <CardContent className="space-y-2">
                    <p className="text-sm font-medium text-text">
                        {rich
                            ? "What should change so the next one fits better?"
                            : "Anything you'd change? (optional)"}
                    </p>
                    <VoiceControl
                        placeholder="Type or speak…"
                        hint="Type or tap the mic to say what to tweak, then Send."
                        onText={(t) => {
                            onChange({ ...state, tweak: t });
                            setTweakSaved(true);
                        }}
                    />
                    {tweakSaved && (
                        <p className="text-xs font-medium text-accent">
                            Feedback noted: "{state.tweak}"
                        </p>
                    )}
                    {rich && (
                        <p className="text-xs text-text-muted border border-dashed border-border rounded-md p-2 mt-1">
                            What you say here shapes the next Spark.
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
