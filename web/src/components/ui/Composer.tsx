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
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT)}px`;
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
      className="shrink-0 z-30 bg-surface border-t border-divider px-3 flex items-end gap-2"
      style={{
        paddingTop: "8px",
        paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 12px)",
      }}
    >
      <textarea
        ref={textareaRef}
        rows={1}
        value={text}
        onChange={(e) => { setText(e.target.value); }}
        onKeyDown={handleKeyDown}
        placeholder="Type a message…"
        disabled={disabled}
        className="flex-1 resize-none px-4 py-2.5 bg-surface-2 border border-border rounded-lg text-[16px] text-text placeholder:text-text-subtle outline-none transition-[border-color,box-shadow,background-color] duration-200 ease-[var(--ease-out)] hover:border-text-subtle/40 focus:bg-surface focus:border-primary/60 focus:ring-2 focus:ring-focus"
        style={{ maxHeight: `${COMPOSER_MAX_HEIGHT}px` }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        className="w-11 h-11 mb-0.5 rounded-full bg-primary text-on-primary flex items-center justify-center shrink-0 shadow-primary transition-[transform,background-color,box-shadow,opacity] duration-200 ease-[var(--ease-spring)] enabled:hover:bg-primary-hover enabled:hover:scale-105 enabled:active:scale-95 disabled:opacity-40 disabled:shadow-none outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        aria-label="Send"
      >
        <Send className="w-[18px] h-[18px]" />
      </button>
    </div>
  );
}
