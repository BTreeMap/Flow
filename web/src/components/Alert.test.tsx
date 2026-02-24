import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Alert } from "./Alert";

describe("Alert", () => {
  it("renders with default props (variant=info)", () => {
    render(<Alert>Default Alert</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent("Default Alert");
    // Check for info variant classes
    expect(alert).toHaveClass("bg-primary/10");
    expect(alert).toHaveClass("text-primary");
    expect(alert).toHaveClass("border-primary/20");
  });

  it("renders success variant correctly", () => {
    render(<Alert variant="success">Success Alert</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("bg-success/10");
    expect(alert).toHaveClass("text-success");
    expect(alert).toHaveClass("border-success/20");
  });

  it("renders warning variant correctly", () => {
    render(<Alert variant="warning">Warning Alert</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("bg-yellow-500/10");
    expect(alert).toHaveClass("text-yellow-600");
    expect(alert).toHaveClass("border-yellow-500/20");
  });

  it("renders error variant correctly", () => {
    render(<Alert variant="error">Error Alert</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("bg-danger/10");
    expect(alert).toHaveClass("text-danger");
    expect(alert).toHaveClass("border-danger/20");
  });

  it("applies custom className", () => {
    render(<Alert className="custom-class">Custom Class Alert</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("custom-class");
  });

  it("passes data-testid", () => {
    render(<Alert data-testid="test-alert">Test Alert</Alert>);
    const alert = screen.getByTestId("test-alert");
    expect(alert).toBeInTheDocument();
  });
});
