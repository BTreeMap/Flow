import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VoiceControl } from "./VoiceControl";

// In jsdom there is no SpeechRecognition, so the mic is hidden and these tests
// exercise the universal text + Send path that must work on every platform.

describe("VoiceControl", () => {
    it("enables Send when text is present, submits trimmed text, and clears the field", () => {
        const onText = vi.fn();
        render(<VoiceControl placeholder="Type…" onText={onText} />);

        const textarea = screen.getByPlaceholderText("Type…");
        const send = screen.getByRole("button", { name: "Send" });

        expect(send).toBeDisabled();

        fireEvent.change(textarea, { target: { value: "  make it easier  " } });
        expect(send).toBeEnabled();

        fireEvent.click(send);
        expect(onText).toHaveBeenCalledTimes(1);
        expect(onText).toHaveBeenCalledWith("make it easier");
        // Field clears so the composer is ready for the next change.
        expect(textarea).toHaveValue("");
        expect(send).toBeDisabled();
    });

    it("keeps Send disabled for empty or whitespace-only input", () => {
        const onText = vi.fn();
        render(<VoiceControl placeholder="Type…" onText={onText} />);

        const textarea = screen.getByPlaceholderText("Type…");
        const send = screen.getByRole("button", { name: "Send" });

        fireEvent.change(textarea, { target: { value: "   " } });
        expect(send).toBeDisabled();

        fireEvent.click(send);
        expect(onText).not.toHaveBeenCalled();
    });

    it("hides the mic when SpeechRecognition is unavailable but keeps text + Send working", () => {
        const onText = vi.fn();
        render(<VoiceControl placeholder="Type…" onText={onText} />);

        // No mic button on platforms without the Web Speech API (e.g. Firefox).
        expect(screen.queryByRole("button", { name: /record|speak/i })).toBeNull();

        const textarea = screen.getByPlaceholderText("Type…");
        fireEvent.change(textarea, { target: { value: "less awkward" } });
        fireEvent.click(screen.getByRole("button", { name: "Send" }));
        expect(onText).toHaveBeenCalledWith("less awkward");
    });

    it("submits via Ctrl/Cmd+Enter as an additive shortcut", () => {
        const onText = vi.fn();
        render(<VoiceControl placeholder="Type…" onText={onText} />);

        const textarea = screen.getByPlaceholderText("Type…");
        fireEvent.change(textarea, { target: { value: "more energetic" } });

        fireEvent.keyDown(textarea, { key: "Enter", metaKey: true });
        expect(onText).toHaveBeenCalledWith("more energetic");

        fireEvent.change(textarea, { target: { value: "again" } });
        fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });
        expect(onText).toHaveBeenCalledWith("again");
    });
});
