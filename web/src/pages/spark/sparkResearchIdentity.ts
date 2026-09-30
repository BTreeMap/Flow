import { Thumbmark } from "@thumbmarkjs/thumbmarkjs";

const INSTALLATION_ID_KEY = "flow.spark.research-installation-id.v1";

export interface SparkResearchIdentity {
    installation_id: string;
    fingerprint?: string;
    fingerprint_version?: string;
    timezone?: string;
    locale?: string;
}

export type SparkIdentityProvider = () => Promise<SparkResearchIdentity>;

function createUuid(): string {
    const webCrypto = globalThis.crypto;
    if (typeof webCrypto.randomUUID === "function") {
        return webCrypto.randomUUID();
    }

    const bytes = new Uint8Array(16);
    webCrypto.getRandomValues(bytes);
    bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
    bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function getInstallationId(): string {
    try {
        const stored = window.localStorage.getItem(INSTALLATION_ID_KEY);
        if (stored) return stored;

        const installationId = createUuid();
        window.localStorage.setItem(INSTALLATION_ID_KEY, installationId);
        return installationId;
    } catch {
        // Storage can be disabled in private browsing. The session can still
        // participate, but it cannot be linked after the browser closes.
        return createUuid();
    }
}

function getBrowserContext(): Pick<SparkResearchIdentity, "timezone" | "locale"> {
    return {
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || undefined,
        locale: navigator.language || undefined,
    };
}

let identityPromise: Promise<SparkResearchIdentity> | null = null;

/**
 * Resolve the Spark research identity once per page load.
 *
 * ThumbmarkJS runs entirely in the browser here: no API key or endpoint is
 * configured, so its component data never leaves the browser. Only the final
 * thumbmark hash is sent to Flow alongside the localStorage installation id.
 */
export function getSparkResearchIdentity(): Promise<SparkResearchIdentity> {
    if (identityPromise) return identityPromise;

    const baseline: SparkResearchIdentity = {
        installation_id: getInstallationId(),
        ...getBrowserContext(),
    };

    identityPromise = new Thumbmark({ logging: false, cache_lifetime_in_ms: 0 })
        .get()
        .then((result) => ({
            ...baseline,
            ...(result.thumbmark ? { fingerprint: result.thumbmark } : {}),
            ...(result.version ? { fingerprint_version: result.version } : {}),
        }))
        .catch(() => baseline);

    return identityPromise;
}

export function createSparkClientId(): string {
    return createUuid();
}
