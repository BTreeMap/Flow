/**
 * How long the countdown runs for.
 *
 * Rendered identically in every condition, in the same position, with the same
 * wording. That is deliberate: condition A is the no-choice control, so a
 * duration picker that appeared only in some arms would add a second difference
 * between them. Held constant across all four, it is a covariate rather than
 * part of the manipulation -- which is also why `duration_source` travels with
 * every finished run.
 */
import { ChipGroup } from "../../components/ui";
import type { SparkDurationControl } from "./useSparkDuration";
import { formatDuration } from "./sparkDuration";

export function DurationControl({ duration }: { duration: SparkDurationControl }) {
    return (
        <ChipGroup
            label="How long do you want to move for?"
            options={duration.choices.map((seconds) => ({
                value: seconds,
                label: formatDuration(seconds),
            }))}
            value={duration.seconds}
            onSelect={duration.choose}
        />
    );
}
