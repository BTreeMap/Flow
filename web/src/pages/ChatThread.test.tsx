import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MessageBubble } from "../components/ui/MessageBubble";

// Test MessageBubble rendering (unit level) - the ChatThread component
// relies on network calls and SSE which are hard to unit test, so we
// test the presentation components directly.

describe("MessageBubble", () => {
  it("renders user message with outgoing bubble style", () => {
    const { container } = render(
      <MessageBubble role="user" content="Hello!" />,
    );
    expect(container.querySelector(".bg-bubble-out")).toBeInTheDocument();
  });

  it("renders assistant message with incoming bubble style", () => {
    const { container } = render(
      <MessageBubble role="assistant" content="Hi there!" />,
    );
    expect(container.querySelector(".bg-bubble-in")).toBeInTheDocument();
  });

  it("renders system message centered", () => {
    const { container } = render(
      <MessageBubble role="system" content="System message" />,
    );
    expect(container.querySelector(".bg-bubble-system")).toBeInTheDocument();
  });

  it("renders timestamp when provided", () => {
    render(<MessageBubble role="user" content="Hello!" timestamp="10:30 AM" />);
    expect(screen.getByText("10:30 AM")).toBeInTheDocument();
  });

  it("applies group continuation styling", () => {
    const { container } = render(
      <MessageBubble
        role="user"
        content="Second message"
        isGroupContinuation={true}
      />,
    );
    const bubble = container.querySelector(".mt-\\[2px\\]");
    expect(bubble).toBeInTheDocument();
  });

  it("renders user message as plain text (not markdown)", () => {
    render(<MessageBubble role="user" content="**bold** text" />);
    expect(screen.getByText("**bold** text")).toBeInTheDocument();
  });

  it("renders assistant message through Streamdown (markdown)", () => {
    const { container } = render(
      <MessageBubble role="assistant" content="Hello **world**" />,
    );
    // Streamdown renders markdown - check for the bubble container
    expect(container.querySelector(".bg-bubble-in")).toBeInTheDocument();
    // The content should be rendered (Streamdown processes it)
    expect(container.textContent).toContain("Hello");
    expect(container.textContent).toContain("world");
  });

  it("renders debug info with agent and tools when showDebug is true", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Hello"
        showDebug={true}
        debugInfo={{ agent: "COACH", tools: ["propose_profile_patch"] }}
      />,
    );
    expect(screen.getByText("COACH")).toBeInTheDocument();
    expect(screen.getByText(/propose_profile_patch/)).toBeInTheDocument();
  });

  it("renders tool_calls trace in debug mode", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Hello"
        showDebug={true}
        debugInfo={{
          agent: "COACH",
          tools: ["list_schedules"],
          tool_calls: [
            {
              tool: "list_schedules",
              args: { membership_id: 123 },
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("tool calls (1)")).toBeInTheDocument();
    expect(screen.getByText("list_schedules")).toBeInTheDocument();
  });

  it("does not render debug info when showDebug is false", () => {
    const { container } = render(
      <MessageBubble
        role="assistant"
        content="Hello"
        showDebug={false}
        debugInfo={{
          agent: "COACH",
          tools: [],
          tool_calls: [{ tool: "list_schedules", args: {} }],
        }}
      />,
    );
    expect(container.querySelector(".font-mono")).not.toBeInTheDocument();
  });
});
