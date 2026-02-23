import { Streamdown } from "streamdown";

interface AssistantMarkdownProps {
  markdown: string;
  isStreaming?: boolean;
}

/**
 * Renders assistant messages as markdown using Streamdown.
 * Supports both static (completed) and streaming (animated) modes.
 */
export function AssistantMarkdown({
  markdown,
  isStreaming,
}: AssistantMarkdownProps) {
  return (
    <div data-testid="assistant-markdown">
      <Streamdown
        mode={isStreaming ? "streaming" : "static"}
        animated={isStreaming ? true : false}
        isAnimating={isStreaming ?? false}
        className="space-y-2 [&_p]:leading-relaxed [&_ul]:pl-4 [&_ol]:pl-4 [&_li]:my-0.5 [&_pre]:rounded-[var(--radius-sm)] [&_pre]:p-2 [&_pre]:bg-surface-2 [&_pre]:overflow-x-auto [&_pre]:text-[13px] [&_code]:text-[13px] [&_code]:bg-surface-2 [&_code]:px-1 [&_code]:rounded [&_a]:text-primary [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-primary/30 [&_blockquote]:pl-3 [&_blockquote]:text-text-muted"
        skipHtml
      >
        {markdown}
      </Streamdown>
    </div>
  );
}
