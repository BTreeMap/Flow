import { Card, CardContent, SectionHeader } from "../../components";
import { Chip, ScaleControl } from "../../components/ui";
import { ANCHORS, type IntakeProfile } from "./sparkData";

interface CueStepProps {
    profile: IntakeProfile;
    cue: string | null;
    confidence: number | null;
    onCue: (c: string) => void;
    onConfidence: (v: number) => void;
}

const DEFAULT_CUES = [
    "After my next coffee",
    "Before a meeting",
    "Right after lunch",
    "When I feel stiff",
    "Mid-afternoon slump",
];

export function CueStep({ profile, cue, confidence, onCue, onConfidence }: CueStepProps) {
    const anchorDef = profile.anchor ? ANCHORS.find((a) => a.k === profile.anchor) : null;
    const cues = anchorDef
        ? [`When I ${anchorDef.label.toLowerCase()}`, ...DEFAULT_CUES].slice(0, 5)
        : DEFAULT_CUES;

    return (
        <div className="space-y-4">
            <SectionHeader
                size="lg"
                eyebrow="Make it stick"
                title="When would you do this again?"
            />

            <Card>
                <CardContent className="space-y-3">
                    <p className="text-sm font-medium text-text">Pick a cue to repeat it</p>
                    <div className="flex flex-wrap gap-2">
                        {cues.map((c) => (
                            <Chip key={c} selected={cue === c} onClick={() => onCue(c)}>
                                {c}
                            </Chip>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* Confidence (shown once cue picked) */}
            {cue && (
                <Card>
                    <CardContent className="space-y-3">
                        <p className="text-sm font-medium text-text">
                            How confident are you this fits your day?
                        </p>
                        <ScaleControl
                            value={confidence}
                            onPick={onConfidence}
                            lo="Not at all"
                            hi="Very"
                            label="Confidence this fits your day"
                        />
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
