import { get, set, del } from "idb-keyval";

const DB_PRIVATE_KEY = "h4ckath0n_device_private_key";
const DB_PUBLIC_JWK = "h4ckath0n_device_public_jwk";
const DB_DEVICE_ID = "h4ckath0n_device_id";
const DB_USER_ID = "h4ckath0n_user_id";

export interface DeviceKeyMaterial {
  privateKey: CryptoKey;
  publicJwk: JsonWebKey;
}

export interface DeviceIdentity {
  deviceId: string;
  userId: string;
}

export async function ensureDeviceKeyMaterial(): Promise<DeviceKeyMaterial> {
  const existing = await loadDeviceKeyMaterial();
  if (existing) return existing;
  return generateDeviceKeyMaterial();
}

async function loadDeviceKeyMaterial(): Promise<DeviceKeyMaterial | null> {
  const privateKey = await get<CryptoKey>(DB_PRIVATE_KEY);
  const publicJwk = await get<JsonWebKey>(DB_PUBLIC_JWK);
  if (privateKey && publicJwk) return { privateKey, publicJwk };
  return null;
}

async function generateDeviceKeyMaterial(): Promise<DeviceKeyMaterial> {
  const keyPair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" },
    false, // non-extractable private key
    ["sign", "verify"],
  );
  const publicJwk = await crypto.subtle.exportKey("jwk", keyPair.publicKey);
  await set(DB_PRIVATE_KEY, keyPair.privateKey);
  await set(DB_PUBLIC_JWK, publicJwk);
  return { privateKey: keyPair.privateKey, publicJwk };
}

export async function getPrivateKey(): Promise<CryptoKey | null> {
  return (await get<CryptoKey>(DB_PRIVATE_KEY)) ?? null;
}

export async function getPublicJwk(): Promise<JsonWebKey | null> {
  return (await get<JsonWebKey>(DB_PUBLIC_JWK)) ?? null;
}

export async function getDeviceIdentity(): Promise<DeviceIdentity | null> {
  const deviceId = await get<string>(DB_DEVICE_ID);
  const userId = await get<string>(DB_USER_ID);
  if (deviceId && userId) return { deviceId, userId };
  return null;
}

export async function setDeviceIdentity(
  deviceId: string,
  userId: string,
): Promise<void> {
  await set(DB_DEVICE_ID, deviceId);
  await set(DB_USER_ID, userId);
}

export async function clearDeviceKeyMaterial(): Promise<void> {
  await del(DB_PRIVATE_KEY);
  await del(DB_PUBLIC_JWK);
  await del(DB_DEVICE_ID);
  await del(DB_USER_ID);
}

/**
 * Clear only the authorization binding (device_id + user_id) while
 * preserving the device key pair.  Logout should call this instead of
 * {@link clearDeviceKeyMaterial} so the same key identity can be
 * reused on next login.
 */
export async function clearDeviceAuthorization(): Promise<void> {
  await del(DB_DEVICE_ID);
  await del(DB_USER_ID);
}
