import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Input } from "./Input";

describe("Input component accessibility", () => {
  it("links error message to input via aria-describedby", () => {
    render(<Input label="Email" error="Invalid email address" />);

    const input = screen.getByLabelText("Email");
    const errorMessage = screen.getByText("Invalid email address");

    // Check if input has aria-invalid set to true
    expect(input).toHaveAttribute("aria-invalid", "true");

    // Check if aria-describedby points to the error message ID
    const errorId = errorMessage.getAttribute("id");
    expect(errorId).toBeTruthy();
    expect(input).toHaveAttribute("aria-describedby", errorId);
  });

  it("does not have aria-describedby when there is no error", () => {
    render(<Input label="Username" />);

    const input = screen.getByLabelText("Username");
    expect(input).not.toHaveAttribute("aria-describedby");
    // aria-invalid can be false when there is no error
    expect(input).toHaveAttribute("aria-invalid", "false");
  });
});
