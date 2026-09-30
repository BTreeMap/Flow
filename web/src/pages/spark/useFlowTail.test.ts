import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useFlowTail } from "./useFlowTail";

function setup() {
    const track = vi.fn();
    const hook = renderHook(() => useFlowTail(track));
    return { track, hook };
}

describe("submitFeedback", () => {
    it("does nothing until the first question is answered", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.submitFeedback();
        });
        expect(track).not.toHaveBeenCalled();
    });

    it("emits one event for one answer set", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.setFeedback({ tried: 0, reason: "Felt good", tweak: "" });
        });
        act(() => {
            hook.result.current.submitFeedback();
        });
        expect(track).toHaveBeenCalledTimes(1);
        expect(track).toHaveBeenCalledWith({
            event_type: "feedback_submitted",
            tried: 0,
            reason: "Felt good",
            tweak: "",
        });
    });

    it("does not re-emit unchanged answers", () => {
        // The adaptive flow's "try another" chip returns to the card stage
        // without clearing the form, so the feedback screen is reached twice
        // with the same answers. That used to write two research rows under two
        // client event ids, and both persisted.
        const { track, hook } = setup();
        act(() => {
            hook.result.current.setFeedback({ tried: 1, reason: "No time", tweak: "" });
        });
        act(() => {
            hook.result.current.submitFeedback();
            hook.result.current.submitFeedback();
        });
        act(() => {
            hook.result.current.submitFeedback();
        });
        expect(track).toHaveBeenCalledTimes(1);
    });

    it("emits again once an answer actually changes", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.setFeedback({ tried: 1, reason: "No time", tweak: "" });
        });
        act(() => {
            hook.result.current.submitFeedback();
        });
        act(() => {
            hook.result.current.setFeedback({ tried: 1, reason: "Felt awkward", tweak: "" });
        });
        act(() => {
            hook.result.current.submitFeedback();
        });
        expect(track).toHaveBeenCalledTimes(2);
    });
});

describe("feedbackAdjustment", () => {
    it("is null when the participant said nothing", () => {
        const { hook } = setup();
        act(() => {
            hook.result.current.setFeedback({ tried: 0, reason: null, tweak: "   " });
        });
        // The old code fell back to the literal "different" here and asked the
        // model for a different Spark on the participant's behalf.
        expect(hook.result.current.feedbackAdjustment).toBeNull();
    });

    it("prefers the typed tweak over the chosen reason", () => {
        const { hook } = setup();
        act(() => {
            hook.result.current.setFeedback({
                tried: 2,
                reason: "Felt awkward",
                tweak: "  something seated  ",
            });
        });
        expect(hook.result.current.feedbackAdjustment).toBe("something seated");
    });

    it("falls back to the reason when nothing was typed", () => {
        const { hook } = setup();
        act(() => {
            hook.result.current.setFeedback({ tried: 2, reason: "No time", tweak: "" });
        });
        expect(hook.result.current.feedbackAdjustment).toBe("No time");
    });
});

describe("submitCue", () => {
    it("needs a cue", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.submitCue();
        });
        expect(track).not.toHaveBeenCalled();
    });

    it("emits once per distinct cue selection", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.setCue("After my next coffee");
            hook.result.current.setConfidence(4);
        });
        act(() => {
            hook.result.current.submitCue();
            hook.result.current.submitCue();
        });
        expect(track).toHaveBeenCalledTimes(1);
        // No `reminder`: Spark never sent one, so it was never a real answer.
        expect(track).toHaveBeenCalledWith({
            event_type: "cue_selected",
            cue: "After my next coffee",
            confidence: 4,
        });
    });
});

describe("submitCompletion", () => {
    it("is dropped when a rating is missing", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.setRating({ fit: 4, clarity: null, willing: 5 });
        });
        act(() => {
            hook.result.current.submitCompletion();
        });
        expect(track).not.toHaveBeenCalled();
    });

    it("emits once every rating is present", () => {
        const { track, hook } = setup();
        act(() => {
            hook.result.current.setRating({ fit: 4, clarity: 3, willing: 5 });
        });
        act(() => {
            hook.result.current.submitCompletion();
        });
        expect(track).toHaveBeenCalledWith({
            event_type: "condition_completed",
            fit: 4,
            clarity: 3,
            willing: 5,
        });
    });
});
