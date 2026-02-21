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
});
