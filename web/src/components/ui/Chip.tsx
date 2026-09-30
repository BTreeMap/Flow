import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
    children: ReactNode;
    /** Selected state. A chip is a *control*, so selection is its own axis. */
    selected?: boolean;
    /** De-emphasised variant for tertiary actions sitting beside real chips. */
    tone?: "default" | "quiet";
    /**
     * Full-width stacked row instead of an inline pill. Presentation is a
     * separate axis from selection: a stacked option list and a chip row are
     * the same control answering the same question, so they share one
     * implementation rather than drifting as two.
     */
    block?: boolean;
}

/**
 * Canonical selectable pill.
 *
 * `Badge` is the read-only sibling: it renders status, takes no input, and is
 * a `<span>`. Anything the user can pick belongs here, as a real `<button>`
 * carrying `aria-pressed`. Keeping the two apart is what stopped Spark and
 * Settings from each growing their own `.spark-chip` — the split is by
 * *interactivity*, not by appearance, so neither can absorb the other.
 */
export function Chip({
    children,
    selected = false,
    tone = "default",
    block = false,
    className = "",
    ...props
}: ChipProps) {
    const toneClass = tone === "quiet" ? "text-text-muted" : "text-text";
    const stateClass = selected
        ? "bg-text text-bg border-text"
        : `bg-surface border-border hover:bg-surface-2 hover:border-text-subtle ${toneClass}`;

    const shapeClass = block
        ? "flex w-full text-left rounded-md px-4 py-3"
        : "inline-flex rounded-pill px-3.5 py-2";

    return (
        <button
            type="button"
            aria-pressed={selected}
            className={`items-center gap-1.5 border text-sm font-medium ${shapeClass} transition-[background-color,border-color,color] duration-150 ease-[var(--ease-out)] outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-40 disabled:pointer-events-none active:translate-y-px ${stateClass} ${className}`}
            {...props}
        >
            {children}
        </button>
    );
}
