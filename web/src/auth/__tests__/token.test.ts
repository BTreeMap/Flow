import { describe, it, expect, beforeEach } from "vitest";
import { isTokenValid, clearCachedToken, shouldRenewToken } from "../token";

describe("token management", () => {
  beforeEach(() => {
    clearCachedToken();
  });

  it("isTokenValid returns false when no token is cached", () => {
    expect(isTokenValid()).toBe(false);
  });

  it("shouldRenewToken returns true when no token is cached", () => {
    expect(shouldRenewToken()).toBe(true);
  });

  it("clearCachedToken resets state", () => {
    clearCachedToken();
    expect(isTokenValid()).toBe(false);
    expect(shouldRenewToken()).toBe(true);
  });
});
