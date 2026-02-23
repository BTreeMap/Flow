import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AssistantMarkdown } from "./AssistantMarkdown";

describe("AssistantMarkdown", () => {
  it("renders with data-testid attribute", () => {
    render(<AssistantMarkdown markdown="Hello" />);
    expect(screen.getByTestId("assistant-markdown")).toBeInTheDocument();
  });

  it("renders bold text", () => {
    const { container } = render(
      <AssistantMarkdown markdown="This is **bold** text" />,
    );
    expect(container.textContent).toContain("bold");
    expect(container.textContent).toContain("text");
  });

  it("renders inline code", () => {
    const { container } = render(
      <AssistantMarkdown markdown="Use `console.log()` here" />,
    );
    expect(container.textContent).toContain("console.log()");
  });

  it("renders a list", () => {
    const { container } = render(
      <AssistantMarkdown markdown={"- Item one\n- Item two\n- Item three"} />,
    );
    expect(container.textContent).toContain("Item one");
    expect(container.textContent).toContain("Item two");
    expect(container.textContent).toContain("Item three");
  });

  it("does not crash on incomplete markdown", () => {
    // Incomplete bold, unclosed code block
    const { container } = render(
      <AssistantMarkdown markdown={"**unclosed bold\n```\nunclosed code"} />,
    );
    expect(container.textContent).toContain("unclosed bold");
    expect(container.textContent).toContain("unclosed code");
  });

  it("does not crash on empty markdown", () => {
    render(<AssistantMarkdown markdown="" />);
    expect(screen.getByTestId("assistant-markdown")).toBeInTheDocument();
  });
});
