import { describe, it, expect } from "vitest";
import swSource from "../../../public/sw.js?raw";

function toBase64Url(bytes: Uint8Array): string {
  const binary = Array.from(bytes, (b) => String.fromCharCode(b)).join("");
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function createIndexedDbMock(values: Record<string, unknown>): IDBFactory {
  return ({
    open: () => {
      const request: {
        result?: unknown;
        onsuccess?: ((this: unknown, event: Event) => unknown) | null;
      } = {};
      queueMicrotask(() => {
        const db = {
          transaction: () => {
            const tx = {
              objectStore: () => {
                const store = {
                  get: (key: IDBValidKey) => {
                    const req: {
                      result?: unknown;
                      onsuccess?: ((this: unknown, event: Event) => unknown) | null;
                    } = {};
                    queueMicrotask(() => {
                      req.result = values[String(key)] ?? null;
                      req.onsuccess?.call(req, new Event("success"));
                    });
                    return req;
                  },
                };
                return store;
              },
            };
            return tx;
          },
          close: () => {},
        };
        request.result = db;
        request.onsuccess?.call(request, new Event("success"));
      });
      return request;
    },
  }) as unknown as IDBFactory;
}

describe("service worker JWT minting", () => {
  it("uses raw crypto.subtle.sign bytes instead of DER conversion", async () => {
    expect(swSource).not.toContain("derSignatureToJose");
    expect(swSource).toContain(
      "const signature = base64UrlEncode(new Uint8Array(signatureRaw));",
    );
  });

  it("encodes the JWT signature directly from sign() output bytes", async () => {
    expect(swSource).toContain("async function mintHttpToken()");
    expect(swSource).toContain("const signatureRaw = await crypto.subtle.sign(");
    const signatureBytes = new Uint8Array(Array.from({ length: 64 }, (_, i) => i));
    const indexedDB = createIndexedDbMock({
      h4ckath0n_device_private_key: { mock: "private-key" },
      h4ckath0n_device_id: "d1234567890123456789012345678901",
      h4ckath0n_user_id: "u1234567890123456789012345678901",
    });

    const cryptoMock = {
      subtle: {
        sign: async () => signatureBytes.buffer,
      },
    } as unknown as Crypto;

    const btoaMock = (value: string): string =>
      btoa(value);

    const selfMock = {
      location: { origin: "https://example.com" },
      registration: {},
      clients: {},
      addEventListener: () => {},
    };

    const factory = new Function(
      "self",
      "indexedDB",
      "crypto",
      "TextEncoder",
      "btoa",
      `${swSource}; return { mintHttpToken };`,
    ) as (
      self: unknown,
      indexedDB: IDBFactory,
      crypto: Crypto,
      TextEncoder: typeof globalThis.TextEncoder,
      btoa: (value: string) => string,
    ) => { mintHttpToken: () => Promise<string> };

    const { mintHttpToken } = factory(
      selfMock,
      indexedDB,
      cryptoMock,
      TextEncoder,
      btoaMock,
    );
    const token = await mintHttpToken();

    const parts = token.split(".");
    expect(parts).toHaveLength(3);
    expect(parts[2]).toBe(toBase64Url(signatureBytes));
  });
});
