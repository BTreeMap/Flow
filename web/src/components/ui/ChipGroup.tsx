import type { ReactNode } from "react";
import { Chip } from "./Chip";

export interface ChipOption<T> {
    value: T;
    label: ReactNode;
}

interface ChipGroupProps<T> {
    /** Caption above the row. Omit for a bare row inside an existing heading. */
    label?: string;
    options: readonly ChipOption<T>[];
    /**
     * Currently selected value. Omitting `value` entirely makes this an
     * *action* group — chips fire and nothing latches — which is why quick
     * adjustments and navigation shortcuts can share the component with
     * genuine single-select questions.
     */
    value?: T | null;
    onSelect: (value: T) => void;
    disabled?: boolean;
    tone?: "default" | "quiet";
    /** `wrap` for an inline pill row, `stack` for a full-width option list. */
    layout?: "wrap" | "stack";
}

/**
 * Canonical single-select (or action) row of chips.
 *
 * Generic in the option type, so a group over `SparkFrame` cannot be handed a
 * stray string: the callback receives exactly the type the options declared.
 * Every "caption + row of pills" in the app resolves here — previously the
 * same markup was re-typed in five places, each free to drift in padding,
 * selected-state colour and keyboard behaviour.
 */
export function ChipGroup<T extends string | number>({
    label,
    options,
    value,
    onSelect,
    disabled = false,
    tone = "default",
    layout = "wrap",
}: ChipGroupProps<T>) {
    return (
        <div>
            {label && (
                <p className="eyebrow text-text-subtle mb-2">
                    {label}
                </p>
            )}
            <div className={layout === "stack" ? "flex flex-col gap-2" : "flex flex-wrap gap-2"}>
                {options.map((opt) => (
                    <Chip
                        key={String(opt.value)}
                        tone={tone}
                        block={layout === "stack"}
                        selected={value !== undefined && value === opt.value}
                        disabled={disabled}
                        onClick={() => onSelect(opt.value)}
                    >
                        {opt.label}
                    </Chip>
                ))}
            </div>
        </div>
    );
}
