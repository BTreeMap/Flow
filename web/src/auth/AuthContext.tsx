import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import {
  ensureDeviceKeyMaterial,
  getDeviceIdentity,
  setDeviceIdentity,
  clearDeviceAuthorization,
} from "./deviceKey";
import { clearCachedToken } from "./token";
import { publicFetch } from "./api";
import {
  toCreateOptions,
  toGetOptions,
  serializeCreateResponse,
  serializeGetResponse,
} from "./webauthn";
import { useNavigate } from "react-router";

interface User {
  id: string;
  role: string;
  scopes: string[];
}

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  userId: string | null;
  deviceId: string | null;
  role: string | null;
  displayName: string | null;
  /** Backward-compatible user object for existing components */
  user: User | null;
  /** Backward-compatible loading alias */
  loading: boolean;
}

interface AuthContextType extends AuthState {
  register: (displayName: string) => Promise<void>;
  login: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

interface FinishResponse {
  user_id: string;
  device_id: string;
  role?: string;
  display_name?: string;
}

function buildState(
  partial: Omit<AuthState, "user" | "loading">,
): AuthState {
  const user = partial.isAuthenticated && partial.userId
    ? { id: partial.userId, role: partial.role ?? "user", scopes: [] }
    : null;
  return { ...partial, user, loading: partial.isLoading };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(
    buildState({
      isAuthenticated: false,
      isLoading: true,
      userId: null,
      deviceId: null,
      role: null,
      displayName: null,
    }),
  );
  const navigate = useNavigate();

  // Check existing device identity on mount
  useEffect(() => {
    (async () => {
      try {
        const identity = await getDeviceIdentity();
        if (identity) {
          setState(
            buildState({
              isAuthenticated: true,
              isLoading: false,
              userId: identity.userId,
              deviceId: identity.deviceId,
              role: null,
              displayName: null,
            }),
          );
        } else {
          setState((s) => buildState({ ...s, isLoading: false }));
        }
      } catch {
        setState((s) => buildState({ ...s, isLoading: false }));
      }
    })();
  }, []);

  const register = useCallback(
    async (displayName: string) => {
      const keyMaterial = await ensureDeviceKeyMaterial();

      const startRes = await publicFetch<{
        options: Record<string, unknown>;
        flow_id: string;
      }>("/auth/passkey/register/start", {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
      });
      if (!startRes.ok) throw new Error("Registration start failed");

      const createOptions = toCreateOptions(
        startRes.data.options as unknown as Parameters<typeof toCreateOptions>[0],
      );
      const credential = (await navigator.credentials.create(
        createOptions,
      )) as PublicKeyCredential | null;
      if (!credential) throw new Error("Credential creation cancelled");

      const finishRes = await publicFetch<FinishResponse>(
        "/auth/passkey/register/finish",
        {
          method: "POST",
          body: JSON.stringify({
            flow_id: startRes.data.flow_id,
            credential: serializeCreateResponse(credential),
            device_public_key_jwk: keyMaterial.publicJwk,
            device_label: navigator.userAgent.slice(0, 64),
          }),
        },
      );
      if (!finishRes.ok) throw new Error("Registration finish failed");

      await setDeviceIdentity(
        finishRes.data.device_id,
        finishRes.data.user_id,
      );
      setState(
        buildState({
          isAuthenticated: true,
          isLoading: false,
          userId: finishRes.data.user_id,
          deviceId: finishRes.data.device_id,
          role: finishRes.data.role ?? "user",
          displayName: finishRes.data.display_name ?? displayName,
        }),
      );
      navigate("/dashboard");
    },
    [navigate],
  );

  const login = useCallback(async () => {
    const keyMaterial = await ensureDeviceKeyMaterial();

    const startRes = await publicFetch<{
      options: Record<string, unknown>;
      flow_id: string;
    }>("/auth/passkey/login/start", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!startRes.ok) throw new Error("Login start failed");

    const getOptions = toGetOptions(
      startRes.data.options as unknown as Parameters<typeof toGetOptions>[0],
    );
    const credential = (await navigator.credentials.get(
      getOptions,
    )) as PublicKeyCredential | null;
    if (!credential) throw new Error("Login cancelled");

    const finishRes = await publicFetch<FinishResponse>(
      "/auth/passkey/login/finish",
      {
        method: "POST",
        body: JSON.stringify({
          flow_id: startRes.data.flow_id,
          credential: serializeGetResponse(credential),
          device_public_key_jwk: keyMaterial.publicJwk,
          device_label: navigator.userAgent.slice(0, 64),
        }),
      },
    );
    if (!finishRes.ok) throw new Error("Login finish failed");

    await setDeviceIdentity(
      finishRes.data.device_id,
      finishRes.data.user_id,
    );
    setState(
      buildState({
        isAuthenticated: true,
        isLoading: false,
        userId: finishRes.data.user_id,
        deviceId: finishRes.data.device_id,
        role: finishRes.data.role ?? "user",
        displayName: finishRes.data.display_name ?? null,
      }),
    );
    navigate("/dashboard");
  }, [navigate]);

  const logout = useCallback(async () => {
    clearCachedToken();
    await clearDeviceAuthorization();
    setState(
      buildState({
        isAuthenticated: false,
        isLoading: false,
        userId: null,
        deviceId: null,
        role: null,
        displayName: null,
      }),
    );
    navigate("/");
  }, [navigate]);

  return (
    <AuthContext.Provider value={{ ...state, register, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
