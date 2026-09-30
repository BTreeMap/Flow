import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { Spark } from "./Spark";

const mockPost = vi.fn();

vi.mock("../api/client", () => ({
    default: {
        POST: (...args: unknown[]) => mockPost(...args),
    },
}));

vi.mock("./spark/sparkResearchIdentity", () => ({
    createSparkClientId: () => "00000000-0000-4000-8000-000000000001",
    getSparkResearchIdentity: async () => ({
        installation_id: "00000000-0000-4000-8000-000000000002",
        fingerprint: "test-thumbmark",
        fingerprint_version: "1.10.0",
        timezone: "America/Toronto",
        locale: "en-CA",
    }),
}));

vi.mock("./spark/sparkTelemetry", () => ({
    useSparkEventTracker: () => vi.fn(),
}));

// Minimal card fixture
const CARD = {
    title: "Desk Reset",
    frame: "calm",
    action: "Roll your shoulders and breathe.",
    reward: "You feel less tension.",
    why: "Desk-friendly and quick.",
    fit_score: 80,
};

const SUCCESS_RESPONSE = {
    data: {
        condition: "A",
        cards: [CARD],
        model: "gpt-test-model",
        prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
    },
    error: undefined,
};

/** One card per vibe — the shape condition B's sampler is served. */
const SAMPLER_CARDS = ["calm", "zoomies", "silly", "challenge", "science"].map((frame) => ({
    ...CARD,
    frame,
    title: `${frame} sample`,
}));

function respondWith(condition: string, cards: unknown[]) {
    return {
        data: {
            condition,
            cards,
            model: "static-library",
            prompt_version: { prompt_file: "x", prompt_sha256: "y" },
        },
        error: undefined,
    };
}

/** Answer the intake — it asks about circumstances only, never about a vibe. */
async function answerIntake() {
    fireEvent.click(await screen.findByText("Make coffee or tea"));
    fireEvent.click(await screen.findByText("Reach & Roll"));
}

describe("Spark page", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // The duration choice is remembered across flows on purpose, so each
        // test has to start from "never chosen" to exercise the default.
        window.localStorage.clear();
    });

    it("renders the Spark page and home grid", () => {
        render(<Spark />);
        expect(screen.getByTestId("spark-page")).toBeInTheDocument();
        expect(screen.getByTestId("spark-heading")).toBeInTheDocument();
        // All four condition cards are present on home
        expect(screen.getByTestId("spark-cond-A")).toBeInTheDocument();
        expect(screen.getByTestId("spark-cond-D")).toBeInTheDocument();
    });

    it("condition A: fetches on entry, with no base_card and empty history", async () => {
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);

        // Entering the condition IS the request — no second tap to confirm it,
        // which is also what keeps A in step with B's sampler.
        fireEvent.click(screen.getByTestId("spark-cond-A"));

        await waitFor(() => {
            // objectContaining on the outer options too: every request now also
            // carries an AbortSignal so an unmount cancels it in flight.
            expect(mockPost).toHaveBeenCalledWith(
                "/spark/generate",
                expect.objectContaining({
                    body: expect.objectContaining({
                        identity: expect.objectContaining({
                            installation_id: "00000000-0000-4000-8000-000000000002",
                            fingerprint: "test-thumbmark",
                        }),
                        condition: "A",
                        adjustment_history: [],
                    }),
                }),
            );
        });

        // base_card should NOT be present (or undefined) on first generate
        const firstCall = mockPost.mock.calls[0];
        const callBody = (firstCall?.[1] as { body: Record<string, unknown> } | undefined)?.body;
        expect(callBody?.base_card).toBeUndefined();

        // Spark card title visible after generation
        expect(await screen.findByText("Desk Reset")).toBeInTheDocument();
    });

    it("auto-fetching conditions request exactly once on entry", async () => {
        // The once-only guard lives in useSparkRemix, so a re-render (or
        // StrictMode's double effect) must not fire a second generate — which
        // would also double-count the participant's flow in the telemetry.
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        const { rerender } = render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));
        await screen.findByTestId("spark-sample-calm");

        rerender(<Spark />);
        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
    });

    it("adjust (conditions C/D only) sends base_card + accumulated adjustment_history", async () => {
        // Intake → generate (C) succeeds with a card
        mockPost.mockResolvedValueOnce({
            data: {
                condition: "C",
                cards: [CARD],
                model: "gpt-test-model",
                prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
            },
            error: undefined,
        });
        // Second call (remix) also succeeds
        mockPost.mockResolvedValueOnce({
            data: {
                condition: "C",
                cards: [{ ...CARD, title: "Desk Reset (Remix)" }],
                model: "gpt-test-model",
                prompt_version: { prompt_file: "spark_proxy_system", prompt_sha256: "abc" },
            },
            error: undefined,
        });

        render(<Spark />);

        // Enter condition C (adaptive) and answer the intake questions
        fireEvent.click(screen.getByTestId("spark-cond-C"));
        await answerIntake();

        // First (intake) generate fires with no base_card + empty history
        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
        const firstBody = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> } | undefined)?.body;
        expect(firstBody?.condition).toBe("C");
        expect(firstBody?.base_card).toBeUndefined();
        expect(firstBody?.adjustment_history).toEqual([]);
        // The intake states no vibe — the model picks one.
        expect(firstBody?.frame_preference).toBeUndefined();

        // Adapted card appears, with the adjust panel (C/D keep remix)
        await screen.findByText("Desk Reset");

        // Click "Make it easier" quick chip
        fireEvent.click(await screen.findByText("Make it easier"));

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(2);
        });

        const remixCall = (mockPost.mock.calls[1]?.[1] as { body: Record<string, unknown> } | undefined)?.body;
        // base_card should be the prior card
        expect(remixCall?.base_card).toMatchObject({ title: "Desk Reset" });
        // history carries the adjustment
        expect(remixCall?.adjustment_history).toEqual(["make it easier"]);
    });

    it("condition B: shows one real Spark per vibe on entry instead of asking for a vibe", async () => {
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));

        // The sampler loads itself — no vibe question stands between the
        // participant and the intervention.
        await screen.findByTestId("spark-sample-calm");
        expect(mockPost).toHaveBeenCalledTimes(1);
        const body = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
        expect(body.condition).toBe("B");
        expect(body.frame_preference).toBeUndefined();

        // Every vibe is represented by a concrete Spark.
        for (const frame of ["calm", "zoomies", "silly", "challenge", "science"]) {
            expect(screen.getByTestId(`spark-sample-${frame}`)).toBeInTheDocument();
        }

        // Picking one carries that card straight through — no extra fetch.
        fireEvent.click(screen.getByTestId("spark-sample-silly"));
        expect(await screen.findByTestId("spark-card")).toBeInTheDocument();
        expect(screen.getByText("silly sample")).toBeInTheDocument();
        expect(mockPost).toHaveBeenCalledTimes(1);
    });

    it("condition D: browses a ranked catalog holding one Spark per vibe", async () => {
        const catalog = ["calm", "zoomies", "silly", "challenge", "science"].map(
            (frame, i) => ({ ...CARD, frame, fit_score: 95 - i * 5, title: `${frame} pick` }),
        );
        mockPost.mockResolvedValue(respondWith("D", catalog));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-D"));
        await answerIntake();

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
        const body = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
        // One request for the whole catalog, no vibe asked for. The card count
        // is the server's call now, so the client must not send one.
        expect(body).toMatchObject({ condition: "D" });
        expect(body.count).toBeUndefined();
        expect(body.frame_preference).toBeUndefined();

        // Same choice set as condition B's sampler: every vibe, exactly once.
        for (const frame of ["calm", "zoomies", "silly", "challenge", "science"]) {
            expect(screen.getByTestId(`spark-ranked-${frame}`)).toBeInTheDocument();
        }

        // Picking lands on the preview step, whose index is derived from the
        // intake length — not a hardcoded one that drifts when questions change.
        fireEvent.click(screen.getByTestId("spark-ranked-challenge"));
        expect(await screen.findByTestId("spark-card")).toBeInTheDocument();
        expect(screen.getByText("Your pick")).toBeInTheDocument();
    });


    it("runs the study default until the participant picks a length", async () => {
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-A"));

        await screen.findByTestId("spark-card");
        expect(screen.getByText("⏱ 1 minute")).toBeInTheDocument();

        // The control is identical in every condition, which is what keeps it a
        // covariate rather than a second difference between the arms.
        fireEvent.click(screen.getByText("3 minutes"));
        expect(screen.getByText("⏱ 3 minutes")).toBeInTheDocument();
    });

    it("remembers the chosen length for the next flow", async () => {
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        const first = render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-A"));
        await screen.findByTestId("spark-card");
        fireEvent.click(screen.getByText("90 seconds"));
        expect(screen.getByText("⏱ 90 seconds")).toBeInTheDocument();
        first.unmount();

        // A configurable duration must not become a choice task repeated on
        // every single flow.
        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-A"));
        await screen.findByTestId("spark-card");
        expect(screen.getByText("⏱ 90 seconds")).toBeInTheDocument();
    });

    it("honours the countdown policy the server served", async () => {
        mockPost.mockResolvedValue({
            data: {
                condition: "A",
                cards: [CARD],
                model: "static-library",
                prompt_version: { prompt_file: "x", prompt_sha256: "y" },
                timer: { default_seconds: 120, choices: [60, 120], min_seconds: 15, max_seconds: 300 },
            },
            error: undefined,
        });

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-A"));

        await screen.findByTestId("spark-card");
        expect(screen.getByText("⏱ 2 minutes")).toBeInTheDocument();
        // Only what the policy offered.
        expect(screen.queryByText("5 minutes")).not.toBeInTheDocument();
    });

    it("keeps the study design out of the participant-facing copy", async () => {
        // The flows used to name the condition on their first screen, state the
        // hypothesis ("tests whether simply delivering a short action is
        // enough"), and label the outcome measures with the names the analysis
        // uses for them.
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);
        expect(screen.queryByText(/research prototype/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/who chooses/i)).not.toBeInTheDocument();

        fireEvent.click(screen.getByTestId("spark-cond-A"));
        await screen.findByTestId("spark-card");
        expect(screen.queryByText(/Condition A/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/chosen at random/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Tests whether/i)).not.toBeInTheDocument();
    });


    it("asks nothing it does not use", async () => {
        // Every intake answer has to reach the generated Spark. The time-of-day
        // question did not: it asked when to send a reminder, nothing schedules
        // one, and the answer only ever became "time: Morning" in the context
        // for a move the participant does immediately.
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-C"));
        await answerIntake();

        expect(screen.queryByText("Morning")).not.toBeInTheDocument();
        expect(screen.queryByText(/when should we remind you/i)).not.toBeInTheDocument();

        await waitFor(() => {
            expect(mockPost).toHaveBeenCalledTimes(1);
        });
        const body = (mockPost.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
        // The model gets the label the participant read, not the stored slug.
        expect(body.context).toBe(
            "anchor: right after your coffee or tea; preferred move: Reach & Roll",
        );
    });

    it("shows the API's own reason for a failure, not a blanket message", async () => {
        // A missing key, a bad model payload and a timeout all used to render
        // identically, which made the UI useless for diagnosis.
        mockPost.mockResolvedValue({
            data: undefined,
            error: { detail: "OpenAI API key not configured" },
        });

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));

        expect(await screen.findByTestId("spark-error")).toHaveTextContent(
            "OpenAI API key not configured",
        );
    });

    it("falls back to a generic message when the API gives no usable detail", async () => {
        mockPost.mockResolvedValue({ data: undefined, error: { detail: [] } });

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));

        expect(await screen.findByTestId("spark-error")).toHaveTextContent(
            "Spark generation failed",
        );
    });

    it("leaves a condition through the home control", async () => {
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));
        expect(await screen.findByText("Which one would you actually do?")).toBeInTheDocument();

        // Leaving is its own control, always available and always deliberate.
        fireEvent.click(screen.getByLabelText("Back to the start"));
        expect(screen.getByTestId("spark-cond-A")).toBeInTheDocument();
    });

    it("disables back on the first step instead of making it exit", async () => {
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));
        await screen.findByText("Which one would you actually do?");

        // One control doing two jobs is how "back" used to become "leave"
        // without saying so.
        expect(screen.getByLabelText("Previous step")).toBeDisabled();
        expect(screen.getByLabelText("Back to the start")).toBeEnabled();
    });

    it("steps back through a flow without leaving it", async () => {
        mockPost.mockResolvedValue(respondWith("B", SAMPLER_CARDS));

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-B"));
        fireEvent.click(await screen.findByTestId("spark-sample-calm"));
        expect(await screen.findByTestId("spark-card")).toBeInTheDocument();

        fireEvent.click(screen.getByLabelText("Previous step"));
        expect(await screen.findByText("Which one would you actually do?")).toBeInTheDocument();
        // Still inside the condition, not back on the home grid.
        expect(screen.queryByTestId("spark-cond-A")).not.toBeInTheDocument();
    });

    it("disables back on the generate step rather than silently exiting", async () => {
        // This was the surprising one: stepping back from a generated Spark
        // would re-fire a paid model call, so the shared control exited to the
        // home grid instead — with no indication that it would.
        mockPost.mockResolvedValue(SUCCESS_RESPONSE);

        render(<Spark />);
        fireEvent.click(screen.getByTestId("spark-cond-C"));
        await answerIntake();
        await screen.findByTestId("spark-card");

        expect(screen.getByLabelText("Previous step")).toBeDisabled();
        fireEvent.click(screen.getByLabelText("Back to the start"));
        expect(screen.getByTestId("spark-cond-A")).toBeInTheDocument();
    });
});
