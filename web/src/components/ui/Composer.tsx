import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";

const COMPOSER_MAX_HEIGHT = 80;

interface ComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT) + "px";
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className="sticky bottom-0 z-30 bg-surface border-t border-divider px-3 flex items-end gap-2"
      style={{
        paddingTop: "8px",
        paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 12px)",
      }}
    >
      <textarea
        ref={textareaRef}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message…"
        disabled={disabled}
        className="flex-1 resize-none px-4 py-2.5 bg-surface-2 border border-border rounded-[var(--radius-pill)] text-[15px] text-text placeholder:text-text-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-focus transition-colors"
        style={{ maxHeight: `${COMPOSER_MAX_HEIGHT}px` }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        className="w-10 h-10 mb-0.5 rounded-full bg-primary text-on-primary flex items-center justify-center shrink-0 disabled:opacity-40 transition-colors hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        aria-label="Send"
      >
        <Send className="w-[18px] h-[18px]" />
      </button>
    </div>
  );
}
