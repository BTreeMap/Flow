/**
 * VoiceControl — unified voice + text composer (Web Speech API + textarea).
 *
 * Renders an editable textarea with a trailing action column (mic + Send):
 *   - Typing or dictation both fill the SAME textarea; dictation appends to
 *     (never replaces) existing text.
 *   - The mic toggles a continuous recognition session. Stopping does NOT
 *     submit — the transcript stays in the field for review/editing.
 *   - A single Send button commits both paths (disabled while empty). This is
 *     the only submit affordance that works on mobile touch keyboards.
 *   - Ctrl/Cmd+Enter is an additive power-user shortcut for the same submit.
 *   - When SpeechRecognition is unavailable (e.g. Firefox), the mic is hidden
 *     entirely; the textarea + Send remain fully functional and the device
 *     keyboard's own dictation still works.
 *
 * Does NOT persist state — parent owns the value if needed.
 */
import { useMemo, useRef, useState } from "react";

interface VoiceControlProps {
    placeholder?: string;
    hint?: string;
    onText: (text: string) => void;
    /** Extra class on the outer wrapper */
    className?: string;
}

// ---------------------------------------------------------------------------
// Minimal Web Speech API typings (constructor is not in lib.dom.d.ts globals)
// ---------------------------------------------------------------------------
interface SRResult {
    readonly isFinal: boolean;
    readonly [index: number]: { readonly transcript: string } | undefined;
}
interface SRResultList {
    readonly length: number;
    readonly [index: number]: SRResult | undefined;
}
interface SREvent {
    readonly resultIndex: number;
    readonly results: SRResultList;
}
interface SRErrorEvent {
    readonly error: string;
}
interface SRInstance {
    lang: string;
    interimResults: boolean;
    continuous: boolean;
    onresult: ((e: SREvent) => void) | null;
    onerror: ((e: SRErrorEvent) => void) | null;
    onend: (() => void) | null;
    start(): void;
    stop(): void;
}
type SRCtor = new () => SRInstance;

/** Vendor-safe SpeechRecognition constructor. Returns null when unavailable. */
function getSR(): SRCtor | null {
    const w = window as unknown as Record<string, unknown>;
    // eslint-disable-next-line @typescript-eslint/dot-notation
    const ctor = w["SpeechRecognition"] ?? w["webkitSpeechRecognition"];
    return typeof ctor === "function" ? (ctor as SRCtor) : null;
}

export function VoiceControl({ placeholder = "Type or speak a change…", hint, onText, className = "" }: VoiceControlProps) {
    const taRef = useRef<HTMLTextAreaElement>(null);
    const recRef = useRef<SRInstance | null>(null);
    // Text present when the current recording started — transcription is
    // APPENDED to this so dictation never wipes what the user already typed.
    const baseTextRef = useRef("");
    const [text, setText] = useState("");
    const [recording, setRecording] = useState(false);

    // SpeechRecognition is only available on Chromium/WebKit; it is absent on
    // Firefox and some embedded webviews. Detect once: when unavailable we hide
    // the mic entirely (never show a dead button) and the textarea + Send still
    // work — the device keyboard's own dictation mic remains usable on mobile.
    const micSupported = useMemo(() => getSR() !== null, []);

    const canSubmit = text.trim().length > 0;

    function stopRecording() {
        setRecording(false);
        try {
            recRef.current?.stop();
        } catch {
            // ignore
        }
        recRef.current = null;
    }

    function submit() {
        // Submitting while still recording: stop the mic first so we don't leave
        // a dangling recognition session running in the background.
        if (recording) stopRecording();
        const v = text.trim();
        if (!v) return;
        onText(v);
        setText("");
        baseTextRef.current = "";
    }

    function startRecording() {
        const SR = getSR();
        if (!SR) {
            taRef.current?.focus();
            return;
        }

        const rec = new SR();
        rec.lang = "en-US";
        rec.interimResults = true;
        // Keep listening until the user explicitly stops. With continuous=false,
        // browsers auto-stop after the first pause in speech (~3-5s), which
        // ignores the user's intent. continuous=true keeps the session open;
        // only an explicit stop tap or a hard error ends it. Stopping does NOT
        // submit — the transcript lands in the editable field for review, and
        // the shared Send button commits it (mainstream dictate-into-field UX).
        rec.continuous = true;
        recRef.current = rec;

        // Anchor on whatever is already in the field so we append, not replace.
        const base = text.trim();
        baseTextRef.current = base;
        let finalText = "";

        rec.onresult = (e: SREvent) => {
            let interim = "";
            for (let i = e.resultIndex; i < e.results.length; i++) {
                const result = e.results[i];
                if (!result) continue;
                const tr = result[0]?.transcript ?? "";
                if (result.isFinal) finalText += tr;
                else interim += tr;
            }
            const spoken = (finalText + " " + interim).trim();
            setText([baseTextRef.current, spoken].filter(Boolean).join(" "));
        };

        rec.onerror = () => {
            stopRecording();
            taRef.current?.focus();
        };

        // Safety net only: keep UI state in sync if the browser ends the session
        // on its own (e.g. iOS Safari ignores continuous, mic permission lost).
        // Never submits — the text simply stays in the field for the user.
        rec.onend = () => {
            setRecording(false);
        };

        setRecording(true);
        try {
            rec.start();
        } catch {
            setRecording(false);
        }
    }

    function toggleMic() {
        if (recording) stopRecording();
        else startRecording();
    }

    return (
        <div className={`space-y-1.5 ${className}`}>
            <div className="flex items-end gap-2 rounded-lg border border-border bg-surface p-2 focus-within:border-primary focus-within:ring-3 focus-within:ring-focus transition-[border-color,box-shadow]">
                <textarea
                    ref={taRef}
                    className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-text placeholder:text-text-subtle outline-none"
                    placeholder={placeholder}
                    rows={2}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => {
                        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                            e.preventDefault();
                            submit();
                        }
                    }}
                />
                <div className="flex items-center gap-1 shrink-0">
                    {micSupported && (
                        <button
                            type="button"
                            className={`spark-mic-btn grid place-items-center w-10 h-10 rounded-full border transition-colors outline-none focus-visible:ring-2 focus-visible:ring-focus ${
                                recording
                                    ? "bg-danger border-danger text-on-danger"
                                    : "bg-surface-2 border-border text-text-muted hover:text-text hover:border-text-subtle"
                            }`}
                            data-recording={recording ? "true" : "false"}
                            aria-label={recording ? "Stop recording" : "Speak your change"}
                            aria-pressed={recording}
                            onClick={toggleMic}
                        >
                            {recording ? (
                                <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18" aria-hidden="true">
                                    <rect x="6" y="6" width="12" height="12" rx="2" />
                                </svg>
                            ) : (
                                <svg
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    width="20"
                                    height="20"
                                    aria-hidden="true"
                                >
                                    <rect x="9" y="2" width="6" height="12" rx="3" />
                                    <path d="M5 10a7 7 0 0 0 14 0" />
                                    <line x1="12" y1="19" x2="12" y2="22" />
                                </svg>
                            )}
                        </button>
                    )}
                    <button
                        type="button"
                        className="grid place-items-center w-10 h-10 rounded-full bg-primary text-on-primary transition-colors hover:bg-primary-hover disabled:bg-surface-3 disabled:text-text-subtle disabled:cursor-not-allowed outline-none focus-visible:ring-2 focus-visible:ring-focus"
                        aria-label="Send"
                        disabled={!canSubmit}
                        onClick={submit}
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20" aria-hidden="true">
                            <line x1="22" y1="2" x2="11" y2="13" />
                            <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                    </button>
                </div>
            </div>
            {hint && <p className="text-xs text-text-muted">{hint}</p>}
        </div>
    );
}

