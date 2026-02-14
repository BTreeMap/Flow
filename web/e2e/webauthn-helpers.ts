/**
 * Helpers for enabling the Chrome DevTools Protocol (CDP) virtual
 * WebAuthn authenticator in Playwright Chromium tests.
 *
 * This uses `page.context().newCDPSession(page)` to drive the
 * `WebAuthn` domain, allowing fully automated passkey registration
 * and login without any physical authenticator.
 */
import type { CDPSession, Page } from "@playwright/test";

export interface VirtualAuthenticator {
  session: CDPSession;
  authenticatorId: string;
}

/**
 * Attach a virtual WebAuthn authenticator to the given page.
 * Must be called **before** the page triggers `navigator.credentials.*`.
 */
export async function addVirtualAuthenticator(
  page: Page,
): Promise<VirtualAuthenticator> {
  const session = await page.context().newCDPSession(page);
  await session.send("WebAuthn.enable");
  const { authenticatorId } = await session.send(
    "WebAuthn.addVirtualAuthenticator",
    {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    },
  );
  return { session, authenticatorId };
}

/**
 * Remove the virtual authenticator and disable the WebAuthn domain.
 */
export async function removeVirtualAuthenticator(
  auth: VirtualAuthenticator,
): Promise<void> {
  await auth.session.send("WebAuthn.removeVirtualAuthenticator", {
    authenticatorId: auth.authenticatorId,
  });
  await auth.session.send("WebAuthn.disable");
}

/**
 * Get all credentials registered on the virtual authenticator.
 */
export async function getCredentials(
  auth: VirtualAuthenticator,
): Promise<Array<{ credentialId: string; rpId: string }>> {
  const { credentials } = await auth.session.send("WebAuthn.getCredentials", {
    authenticatorId: auth.authenticatorId,
  });
  return credentials as Array<{ credentialId: string; rpId: string }>;
}
