import { beforeEach, describe, expect, it, vi } from "vitest";

const thumbmarkGet = vi.hoisted(() => vi.fn());

vi.mock("@thumbmarkjs/thumbmarkjs", () => ({
    Thumbmark: class {
        get = thumbmarkGet;
    },
}));

const INSTALLATION_ID = "00000000-0000-4000-8000-000000000001";

beforeEach(() => {
    vi.resetModules();
    window.localStorage.clear();
    thumbmarkGet.mockReset();
    vi.stubGlobal("crypto", {
        randomUUID: vi.fn(() => INSTALLATION_ID),
        getRandomValues: vi.fn(),
    });
});

describe("getSparkResearchIdentity", () => {
    it("combines a stable local installation id with the locally generated thumbmark", async () => {
        thumbmarkGet.mockResolvedValue({
            thumbmark: "thumbmark-hash",
            version: "1.10.0",
        });
        const { getSparkResearchIdentity } = await import("./sparkResearchIdentity");

        const identity = await getSparkResearchIdentity();

        expect(identity).toMatchObject({
            installation_id: INSTALLATION_ID,
            fingerprint: "thumbmark-hash",
            fingerprint_version: "1.10.0",
        });
        expect(window.localStorage.getItem("flow.spark.research-installation-id.v1")).toBe(
            INSTALLATION_ID,
        );
    });

    it("continues with the browser-local identifier when fingerprint collection fails", async () => {
        thumbmarkGet.mockRejectedValue(new Error("fingerprint unavailable"));
        const { getSparkResearchIdentity } = await import("./sparkResearchIdentity");

        const identity = await getSparkResearchIdentity();

        expect(identity.installation_id).toBe(INSTALLATION_ID);
        expect(identity.fingerprint).toBeUndefined();
    });
});
