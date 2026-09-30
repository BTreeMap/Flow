/**
 * The home grid.
 *
 * The four option cards are rendered exactly as they were: same layout, same
 * letter badges, same names, same tags. The surrounding prose is not: it used
 * to name the manipulation ("what changes is who chooses and how much the
 * system personalizes"), instruct the reader to step through all four, and
 * label the page a research prototype. That is the study's design, and it does
 * not belong in front of a participant.
 *
 * The research-privacy paragraph stays. It is disclosure, not leakage, and
 * removing it as part of a de-leaking pass would be exactly the wrong trade.
 */
import { Badge, Card } from "../../components";
import { CONDITIONS, type SparkCondition } from "./sparkData";

export function SparkHome({ onStart }: { onStart: (c: SparkCondition) => void }) {
    return (
        <div className="space-y-8">
            <div>
                <p className="eyebrow text-text-subtle">A movement micro-coach</p>
                <h1 className="display-lg text-text mt-3">
                    A small way to move, whenever you need one.
                </h1>
                <p className="text-base text-text-body mt-3 max-w-prose leading-relaxed">
                    Each option below gives you one short movement break to do right now.
                    Pick one to begin — you can adjust the Spark by tapping or by voice.
                </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
                {CONDITIONS.map((c) => (
                    <Card
                        key={c.id}
                        onClick={() => onStart(c.id)}
                        className="p-6 flex flex-col gap-2 min-h-[168px]"
                        data-testid={`spark-cond-${c.id}`}
                    >
                        <div
                            className={`w-9 h-9 rounded-md grid place-items-center text-on-primary text-sm font-medium ${c.letterBg}`}
                        >
                            {c.id}
                        </div>
                        <div className="display-sm text-[1.125rem] text-text mt-1">{c.name}</div>
                        <div className="text-sm text-text-muted">{c.what}</div>
                        <div className="flex gap-1.5 flex-wrap mt-auto pt-2">
                            {c.tags.map((t) => (
                                <Badge key={t}>{t}</Badge>
                            ))}
                        </div>
                    </Card>
                ))}
            </div>

            <div className="space-y-3">
                <p className="text-xs text-text-muted border border-dashed border-border rounded-lg p-4 leading-relaxed">
                    Each one gives you a <strong className="font-medium text-text">Spark card</strong>, a{" "}
                    <strong className="font-medium text-text">countdown you set</strong>, a way to{" "}
                    <strong className="font-medium text-text">adjust it</strong> by tap or voice, a place for{" "}
                    <strong className="font-medium text-text">feedback</strong>, a{" "}
                    <strong className="font-medium text-text">cue</strong> so you can repeat it, and a
                    short <strong className="font-medium text-text">rating</strong>.
                </p>

                <p className="text-xs text-text-muted border border-dashed border-border rounded-lg p-4 leading-relaxed">
                    <strong className="font-medium text-text">Research privacy:</strong> Spark works without an
                    account. To link repeat visits, it uses a random study identifier stored only in this browser
                    plus a browser fingerprint. Flow stores keyed, non-reversible versions—not the raw values.
                    Clearing site data starts a new study identity.
                </p>
            </div>
        </div>
    );
}
