import type { ReactNode } from "react";

export type BadgeTone =
    | "neutral"
    | "primary"
    | "accent"
    | "info"
    | "success"
    | "warning"
    | "danger";

interface BadgeProps {
    children?: ReactNode;
    tone?: BadgeTone;
    /** Render as a small status dot instead of a text pill. */
    dot?: boolean;
    className?: string;
}

const toneClass: Record<BadgeTone, string> = {
    neutral: "bg-surface-3 text-text-muted",
    primary: "bg-primary/10 text-primary",
    accent: "bg-accent/10 text-accent",
    info: "bg-info/10 text-info",
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    danger: "bg-danger/10 text-danger",
};

const dotClass: Record<BadgeTone, string> = {
    neutral: "bg-text-subtle",
    primary: "bg-primary",
    accent: "bg-accent",
    info: "bg-info",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
};

/**
 * Canonical pill / chip / status-dot primitive. Replaces the inline badge
 * patterns previously hand-rolled in MessageBubble, ChatHeader, Admin and
 * ListRow. Variant-driven via `tone`; pass `dot` for a bare status indicator.
 */
export function Badge({
    children,
    tone = "neutral",
    dot = false,
    className = "",
}: BadgeProps) {
    if (dot) {
        return (
            <span
                className={`inline-block w-2 h-2 rounded-full ${dotClass[tone]} ${className}`}
                aria-hidden="true"
            />
        );
    }

    return (
        <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${toneClass[tone]} ${className}`}
        >
            {children}
        </span>
    );
}
