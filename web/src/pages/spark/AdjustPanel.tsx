import type { SparkCard as SparkCardData } from "../../api/types";
import { Chip, ChipGroup } from "../../components/ui";
import { FRAME_ORDER, FRAMINGS, type SparkFrame } from "./sparkData";
import { SparkThinking } from "./SparkThinking";
import { VoiceControl } from "./VoiceControl";

interface AdjustPanelProps {
    card: SparkCardData;
    /** Most recent resolved adjustment label (for "saved" visual), or null */
    lastAdjustment?: string | null;
    loading?: boolean;
    onAdjust: (text: string) => void;
    /** Switch the framing without changing the action */
    onFrameSwitch: (frame: SparkFrame) => void;
    onSave?: () => void;
    saved?: boolean;
}

/** Quick adjustments are *actions*, so the group latches nothing. */
const QUICK_ADJUSTMENTS = [
    { value: "make it easier", label: "Make it easier" },
    { value: "more energetic", label: "More energetic" },
    { value: "less awkward, something more subtle", label: "Less awkward" },
    { value: "give me a different one", label: "Give me another" },
] as const;

const FRAME_OPTIONS = FRAME_ORDER.map((k) => ({
    value: k,
    label: (
        <>
            <span aria-hidden="true">{FRAMINGS[k].emoji}</span> {FRAMINGS[k].short}
        </>
    ),
}));

export function AdjustPanel({
    card,
    lastAdjustment,
    loading = false,
    onAdjust,
    onFrameSwitch,
    onSave,
    saved = false,
}: AdjustPanelProps) {
    const currentFrame = card.frame as SparkFrame;

    return (
        <div className="mt-4 border-t border-divider pt-4 space-y-4">
            {loading && (
                <SparkThinking
                    compact
                    frame={currentFrame}
                    phrases={[
                        "Remixing your Spark…",
                        "Folding in your tweak…",
                        "Reworking it on the fly…",
                        "Adjusting the vibe…",
                    ]}
                />
            )}

            <ChipGroup
                label="Adjust this Spark"
                options={QUICK_ADJUSTMENTS}
                onSelect={onAdjust}
                disabled={loading}
            />

            <ChipGroup
                label="Switch the vibe (same action)"
                options={FRAME_OPTIONS}
                value={currentFrame}
                onSelect={onFrameSwitch}
                disabled={loading}
            />

            <div>
                <p className="eyebrow text-text-subtle mb-2">
                    Or tell it what to change
                </p>
                <VoiceControl
                    placeholder="Type or speak a change…"
                    hint={`Type or tap the mic, then Send — e.g. "make it easier", "I'm at a desk", "less awkward".`}
                    onText={onAdjust}
                />
                {lastAdjustment && (
                    <p className="mt-1.5 text-xs font-medium text-accent">
                        Spark updated: "{lastAdjustment}"
                    </p>
                )}
            </div>

            {onSave && (
                <Chip selected={saved} onClick={onSave}>
                    {saved ? "★ Saved" : "☆ Save this Spark"}
                </Chip>
            )}
        </div>
    );
}
