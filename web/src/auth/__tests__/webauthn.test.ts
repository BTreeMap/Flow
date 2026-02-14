import { describe, it, expect } from "vitest";
import { base64urlEncode, base64urlDecode } from "../webauthn";

describe("base64url helpers", () => {
  it("encodes an ArrayBuffer to base64url string", () => {
    const buffer = new Uint8Array([72, 101, 108, 108, 111]).buffer;
    const encoded = base64urlEncode(buffer);
    // "Hello" in base64 is "SGVsbG8=", base64url removes padding
    expect(encoded).toBe("SGVsbG8");
  });

  it("decodes a base64url string to ArrayBuffer", () => {
    const decoded = base64urlDecode("SGVsbG8");
    const bytes = new Uint8Array(decoded);
    expect(Array.from(bytes)).toEqual([72, 101, 108, 108, 111]);
  });

  it("round-trips correctly", () => {
    const original = new Uint8Array([0, 1, 2, 255, 254, 253, 128, 127]);
    const encoded = base64urlEncode(original.buffer);
    const decoded = new Uint8Array(base64urlDecode(encoded));
    expect(Array.from(decoded)).toEqual(Array.from(original));
  });

  it("handles empty buffer", () => {
    const empty = new Uint8Array(0).buffer;
    const encoded = base64urlEncode(empty);
    expect(encoded).toBe("");
    const decoded = base64urlDecode("");
    expect(new Uint8Array(decoded).length).toBe(0);
  });

  it("handles URL-unsafe characters correctly", () => {
    // bytes that produce + and / in standard base64
    const buffer = new Uint8Array([251, 255, 254]).buffer;
    const encoded = base64urlEncode(buffer);
    expect(encoded).not.toContain("+");
    expect(encoded).not.toContain("/");
    expect(encoded).not.toContain("=");
    // Round-trip
    const decoded = new Uint8Array(base64urlDecode(encoded));
    expect(Array.from(decoded)).toEqual([251, 255, 254]);
  });
});
