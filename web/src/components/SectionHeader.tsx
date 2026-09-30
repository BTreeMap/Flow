import type { ReactNode } from "react";

interface SectionHeaderProps {
  /** Small uppercase caption above the title (editorial eyebrow). */
  eyebrow?: string;
  /** Optional leading glyph. Icon-led and eyebrow-led headings are the same
   *  component because they are the same thing: a titled section boundary. */
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  action?: ReactNode;
  /** `md` for in-page sections, `lg` to open a view or a flow step. */
  size?: "md" | "lg";
}

const titleClass = {
  md: "display-sm text-[1.125rem]",
  lg: "display-sm",
} as const;

/**
 * Canonical section boundary: eyebrow, serif display title, lede, action.
 *
 * The display headline is always serif at weight 400 — the type split is the
 * brand voice, so a section title never renders as bold sans. Both the
 * icon-led form (Admin, Settings) and the eyebrow-led editorial form (Spark
 * flow steps) resolve here, so the two cannot drift into separate components.
 */
export function SectionHeader({
  eyebrow,
  icon,
  title,
  subtitle,
  action,
  size = "md",
}: SectionHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        {icon && <span className="text-primary mt-0.5 shrink-0">{icon}</span>}
        <div>
          {eyebrow && (
            <p className="eyebrow text-text-subtle mb-1">
              {eyebrow}
            </p>
          )}
          <h2 className={`text-text ${titleClass[size]}`}>{title}</h2>
          {subtitle && <p className="text-sm text-text-muted mt-1 max-w-prose">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}
