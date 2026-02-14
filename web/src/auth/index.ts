export { useAuth, AuthProvider } from "./AuthContext";
export {
  ensureDeviceKeyMaterial,
  getDeviceIdentity,
  setDeviceIdentity,
  clearDeviceKeyMaterial,
  getPublicJwk,
  getPrivateKey,
} from "./deviceKey";
export {
  getOrMintToken,
  mintToken,
  clearCachedToken,
  isTokenValid,
  shouldRenewToken,
} from "./token";
export { apiFetch, publicFetch, AuthError, type ApiResponse } from "./api";
export {
  base64urlEncode,
  base64urlDecode,
  toCreateOptions,
  toGetOptions,
  serializeCreateResponse,
  serializeGetResponse,
} from "./webauthn";
export { createAuthWebSocket, sendReauth } from "./ws";
