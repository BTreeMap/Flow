import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Fingerprint,
  Plus,
  Trash2,
  AlertCircle,
  LogOut,
  Smartphone,
  User,
  Save,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router";
import { apiFetch, useAuth } from "../auth";
import { toCreateOptions, serializeCreateResponse } from "../auth/webauthn";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { Alert } from "../components/Alert";
import { SectionHeader } from "../components/SectionHeader";
import { PageHeader } from "../components/ui/PageHeader";
import { PasskeyName } from "../components/settings/PasskeyName";
import { ThemeSection } from "../components/settings/ThemeSection";
import api from "../api/client";
import type {
  AuthSessionItem,
  AuthSessionsResponse,
  PasskeyInfo,
  UserMeResponse,
} from "../api/types";

export function Settings() {
  const queryClient = useQueryClient();
  const { role, logout } = useAuth();
  const [addLoading, setAddLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastPasskeyError, setLastPasskeyError] = useState<string | null>(null);
  const [profileEmail, setProfileEmail] = useState("");
  const [profileDisplayName, setProfileDisplayName] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState(false);

  const { data: profile, isLoading: profileLoading } = useQuery<UserMeResponse>(
    {
      queryKey: ["me"],
      queryFn: async () => {
        const { data, error } = await api.GET("/me");
        if (error) throw new Error("Failed to load profile");
        return data as UserMeResponse;
      },
      // Initialize form fields when data loads
    },
  );

  // Sync form fields when profile data loads/changes
  const [profileInitialized, setProfileInitialized] = useState(false);
  if (profile && !profileInitialized) {
    setProfileEmail(profile.email ?? "");
    setProfileDisplayName(profile.display_name ?? "");
    setProfileInitialized(true);
  }

  const saveProfile = async () => {
    setProfileSaving(true);
    setProfileSuccess(false);
    setError(null);
    try {
      const body: Record<string, string> = {};
      if (profileEmail.trim()) body.email = profileEmail.trim();
      if (profileDisplayName.trim())
        body.display_name = profileDisplayName.trim();
      const { error: apiError } = await api.PATCH("/me", { body });
      if (apiError) throw new Error("Failed to save profile");
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      setProfileSuccess(true);
      setTimeout(() => { setProfileSuccess(false); }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setProfileSaving(false);
    }
  };

  const { data: passkeys, isLoading } = useQuery<PasskeyInfo[]>({
    queryKey: ["passkeys"],
    queryFn: async () => {
      const { data, error } = await api.GET("/auth/passkeys");
      if (error) throw new Error("Failed to load passkeys");
      return data.passkeys;
    },
  });
  const {
    data: sessions,
    isLoading: sessionsLoading,
    isError: sessionsIsError,
    error: sessionsError,
  } = useQuery<AuthSessionItem[]>({
    queryKey: ["sessions"],
    queryFn: async () => {
      const { data, error } = await api.GET("/auth/sessions");
      if (error) throw new Error("Failed to load sessions");
      return (data as AuthSessionsResponse).sessions ?? [];
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (passkeyId: string) => {
      setLastPasskeyError(null);
      const res = await apiFetch(`/auth/passkeys/${passkeyId}/revoke`, {
        method: "POST",
      });
      if (!res.ok) {
        const data = res.data as {
          error?: string;
          detail?: string | { code?: string; message?: string };
        };
        const detail = data.detail;
        if (
          data.error === "LAST_PASSKEY" ||
          (typeof detail === "string" && detail.includes("LAST_PASSKEY")) ||
          (typeof detail === "object" && detail?.code === "LAST_PASSKEY")
        ) {
          throw new Error("LAST_PASSKEY");
        }
        const msg =
          typeof detail === "string"
            ? detail
            : (detail as { message?: string })?.message || "Revoke failed";
        throw new Error(msg);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["passkeys"] });
    },
    onError: (err: Error) => {
      if (err.message === "LAST_PASSKEY") {
        setLastPasskeyError(
          "Cannot revoke your last active passkey. Add another passkey first to maintain account access.",
        );
      } else {
        setError(err.message);
      }
    },
  });
  const revokeSessionMutation = useMutation({
    mutationFn: async (deviceId: string) => {
      const { error } = await api.POST("/auth/sessions/{device_id}/revoke", {
        params: { path: { device_id: deviceId } },
      });
      if (error) throw new Error("Failed to revoke session");
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleAddPasskey = async () => {
    setAddLoading(true);
    setError(null);
    try {
      const startRes = await apiFetch<{
        options: Record<string, unknown>;
        flow_id: string;
      }>("/auth/passkey/add/start", { method: "POST" });
      if (!startRes.ok) throw new Error("Failed to start passkey addition");

      const createOptions = toCreateOptions(
        startRes.data.options as unknown as Parameters<
          typeof toCreateOptions
        >[0],
      );
      const credential = (await navigator.credentials.create(
        createOptions,
      )) as PublicKeyCredential | null;
      if (!credential) throw new Error("Passkey creation cancelled");

      const finishRes = await apiFetch("/auth/passkey/add/finish", {
        method: "POST",
        body: JSON.stringify({
          flow_id: startRes.data.flow_id,
          credential: serializeCreateResponse(credential),
        }),
      });
      if (!finishRes.ok) throw new Error("Failed to add passkey");

      void queryClient.invalidateQueries({ queryKey: ["passkeys"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add passkey");
    } finally {
      setAddLoading(false);
    }
  };

  const activePasskeys = passkeys?.filter((p) => !p.revoked_at) ?? [];

  return (
    <div className="flex flex-col flex-1 bg-bg">
      <PageHeader title="Settings" data-testid="settings-heading" />
      <div className="space-y-6 px-4 py-6 max-w-2xl mx-auto w-full">

        {error && (
          <Alert variant="error" data-testid="settings-error">
            {error}
          </Alert>
        )}
        {lastPasskeyError && (
          <Alert variant="warning" data-testid="last-passkey-error">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{lastPasskeyError}</span>
            </div>
          </Alert>
        )}

        <Card>
          <CardHeader>
            <SectionHeader
              icon={<User className="w-5 h-5" />}
              title="Profile"
              subtitle="Your email and display name"
            />
          </CardHeader>
          <CardContent className="space-y-3">
            {profileLoading ? (
              <p className="text-sm text-text-muted">Loading…</p>
            ) : (
              <>
                <Input
                  label="Email"
                  type="email"
                  placeholder="you@example.com"
                  value={profileEmail}
                  onChange={(e) => { setProfileEmail(e.target.value); }}
                  data-testid="profile-email"
                />
                <Input
                  label="Display Name"
                  placeholder="Your name"
                  value={profileDisplayName}
                  onChange={(e) => { setProfileDisplayName(e.target.value); }}
                  data-testid="profile-display-name"
                />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => void saveProfile()}
                    disabled={profileSaving}
                    data-testid="profile-save"
                  >
                    <Save className="w-4 h-4" />
                    {profileSaving ? "Saving…" : "Save"}
                  </Button>
                  {profileSuccess && (
                    <span className="text-sm text-success">Saved!</span>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <ThemeSection />

        <Link
          to="/spark"
          className="flex items-center gap-3 px-4 py-3 bg-surface border border-border rounded-2xl hover:bg-surface-2 transition-colors"
          data-testid="settings-spark-link"
        >
          <span className="text-[15px] font-medium text-text">Open Spark Prototype</span>
        </Link>

        <Card>
          <CardHeader>
            <SectionHeader
              icon={<Smartphone className="w-5 h-5" />}
              title="Devices"
              subtitle="Manage signed-in devices"
            />
          </CardHeader>
          <CardContent>
            {sessionsLoading ? (
              <p className="text-sm text-text-muted">Loading…</p>
            ) : sessionsIsError ? (
              <Alert variant="error" data-testid="sessions-error">
                {sessionsError?.message || "Failed to load devices"}
              </Alert>
            ) : sessions && sessions.length > 0 ? (
              <div className="divide-y divide-border">
                {sessions.map((session) => (
                  <div
                    key={session.device_id}
                    className="flex items-center justify-between py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-text">
                        {session.label || "Unnamed device"}
                        {session.is_current && (
                          <span className="ml-2 text-xs text-primary">
                            Current
                          </span>
                        )}
                        {session.revoked_at && (
                          <span className="ml-2 text-xs text-danger">
                            (revoked)
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-text-muted font-mono">
                        {session.device_id}
                      </p>
                    </div>
                    {!session.revoked_at && !session.is_current && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => { revokeSessionMutation.mutate(session.device_id); }
                        }
                      >
                        <LogOut className="w-3 h-3" />
                        Revoke
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-muted py-4 text-center">
                No devices found.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <SectionHeader
              icon={<Fingerprint className="w-5 h-5" />}
              title="Passkeys"
              subtitle={`${activePasskeys.length} active`}
              action={
                <Button
                  size="sm"
                  onClick={() => void handleAddPasskey()}
                  disabled={addLoading}
                  data-testid="add-passkey-btn"
                >
                  <Plus className="w-4 h-4" />
                  {addLoading ? "Adding..." : "Add Passkey"}
                </Button>
              }
            />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
              </div>
            ) : passkeys && passkeys.length > 0 ? (
              <div className="divide-y divide-border">
                {passkeys.map((passkey) => (
                  <div
                    key={passkey.id}
                    className="flex items-center justify-between py-3"
                    data-testid="passkey-item"
                  >
                    <div>
                      <div className="text-sm font-medium text-text">
                        <PasskeyName
                          passkey={passkey}
                          onRenamed={() =>
                            void queryClient.invalidateQueries({
                              queryKey: ["passkeys"],
                            })
                          }
                        />
                        {passkey.revoked_at && (
                          <span className="ml-2 text-xs text-danger">
                            (revoked)
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-text-muted font-mono">
                        {passkey.id}
                      </p>
                      <p className="text-xs text-text-muted">
                        Created:{" "}
                        {new Date(passkey.created_at).toLocaleDateString()}
                        {passkey.last_used_at && (
                          <>
                            {" "}
                            | Last used:{" "}
                            {new Date(passkey.last_used_at).toLocaleDateString()}
                          </>
                        )}
                      </p>
                    </div>
                    {!passkey.revoked_at && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => { revokeMutation.mutate(passkey.id); }}
                        disabled={revokeMutation.isPending}
                        data-testid="revoke-passkey-btn"
                      >
                        <Trash2 className="w-3 h-3" />
                        Revoke
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-muted py-4 text-center">
                No passkeys found.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Admin entry for admins */}
        {role === "admin" && (
          <Link
            to="/admin"
            className="flex items-center gap-3 px-4 py-3 bg-surface border border-border rounded-2xl hover:bg-surface-2 transition-colors"
            data-testid="settings-admin-link"
          >
            <ShieldCheck className="w-5 h-5 text-primary" />
            <span className="text-[15px] font-medium text-text">Admin Panel</span>
          </Link>
        )}

        {/* Logout */}
        <button
          onClick={() => void logout()}
          className="flex items-center gap-3 w-full px-4 py-3 bg-surface border border-border rounded-2xl hover:bg-surface-2 transition-colors"
          data-testid="settings-logout"
        >
          <LogOut className="w-5 h-5 text-danger" />
          <span className="text-[15px] font-medium text-danger">Log Out</span>
        </button>
      </div>
    </div>
  );
}
