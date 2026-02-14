export function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let str = "";
  for (const byte of bytes) {
    str += String.fromCharCode(byte);
  }
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function base64urlDecode(str: string): ArrayBuffer {
  const padded = str.replace(/-/g, "+").replace(/_/g, "/");
  const padding = (4 - (padded.length % 4)) % 4;
  const base64 = padded + "=".repeat(padding);
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

interface ServerPublicKeyOptions {
  challenge: string;
  rp?: { name: string; id: string };
  rpId?: string;
  user?: { id: string; name: string; displayName: string };
  pubKeyCredParams?: Array<{ type: string; alg: number }>;
  timeout?: number;
  attestation?: string;
  authenticatorSelection?: {
    authenticatorAttachment?: string;
    residentKey?: string;
    requireResidentKey?: boolean;
    userVerification?: string;
  };
  excludeCredentials?: Array<{
    id: string;
    type: string;
    transports?: string[];
  }>;
  allowCredentials?: Array<{
    id: string;
    type: string;
    transports?: string[];
  }>;
  userVerification?: string;
}

export function toCreateOptions(
  serverOptions: ServerPublicKeyOptions,
): CredentialCreationOptions {
  if (!serverOptions.rp) {
    throw new Error("WebAuthn registration requires rp data");
  }
  const publicKey: PublicKeyCredentialCreationOptions = {
    challenge: base64urlDecode(serverOptions.challenge),
    rp: serverOptions.rp,
    user: serverOptions.user
      ? {
          id: base64urlDecode(serverOptions.user.id),
          name: serverOptions.user.name,
          displayName: serverOptions.user.displayName,
        }
      : (() => {
          throw new Error("WebAuthn registration requires user data");
        })(),
    pubKeyCredParams: (serverOptions.pubKeyCredParams ?? []).map((p) => ({
      type: p.type as PublicKeyCredentialType,
      alg: p.alg,
    })),
    timeout: serverOptions.timeout,
    attestation:
      serverOptions.attestation as AttestationConveyancePreference,
    authenticatorSelection:
      serverOptions.authenticatorSelection as AuthenticatorSelectionCriteria,
    excludeCredentials: (serverOptions.excludeCredentials ?? []).map((c) => ({
      id: base64urlDecode(c.id),
      type: c.type as PublicKeyCredentialType,
      transports: c.transports as AuthenticatorTransport[],
    })),
  };
  return { publicKey };
}

export function toGetOptions(
  serverOptions: ServerPublicKeyOptions,
): CredentialRequestOptions {
  const rpId = serverOptions.rpId ?? serverOptions.rp?.id;
  const publicKey: PublicKeyCredentialRequestOptions = {
    challenge: base64urlDecode(serverOptions.challenge),
    rpId,
    timeout: serverOptions.timeout,
    userVerification:
      (serverOptions.userVerification as UserVerificationRequirement) ??
      (serverOptions.authenticatorSelection
        ?.userVerification as UserVerificationRequirement) ?? "preferred",
    allowCredentials: (serverOptions.allowCredentials ?? []).map((c) => ({
      id: base64urlDecode(c.id),
      type: c.type as PublicKeyCredentialType,
      transports: c.transports as AuthenticatorTransport[],
    })),
  };
  return { publicKey };
}

export function serializeCreateResponse(
  credential: PublicKeyCredential,
): Record<string, unknown> {
  const response =
    credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: base64urlEncode(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: base64urlEncode(response.clientDataJSON),
      attestationObject: base64urlEncode(response.attestationObject),
    },
  };
}

export function serializeGetResponse(
  credential: PublicKeyCredential,
): Record<string, unknown> {
  const response =
    credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: base64urlEncode(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: base64urlEncode(response.clientDataJSON),
      authenticatorData: base64urlEncode(response.authenticatorData),
      signature: base64urlEncode(response.signature),
      userHandle: response.userHandle
        ? base64urlEncode(response.userHandle)
        : null,
    },
  };
}
