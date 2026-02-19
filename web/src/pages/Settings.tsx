import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Fingerprint, Plus, Trash2, AlertCircle, Pencil, Check, X } from "lucide-react";
import { apiFetch } from "../auth";
import { toCreateOptions, serializeCreateResponse } from "../auth/webauthn";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import api from "../api/client";
import type { PasskeyInfo } from "../api/types";
import {
  applyThemePreference,
  readThemePreference,
  type ThemePreference,
} from "../theme";

const MAX_NAME_LENGTH = 64;

function PasskeyName({
  passkey,
  onRenamed,
}: {
  passkey: PasskeyInfo;
  onRenamed: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(passkey.name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setDraft(passkey.name ?? "");
    setError(null);
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setError(null);
  };

  const save = async () => {
    const trimmed = draft.trim();
    if (trimmed.length > MAX_NAME_LENGTH) {
      setError(`Name must be ${MAX_NAME_LENGTH} characters or fewer`);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await apiFetch(`/auth/passkeys/${passkey.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: trimmed || null }),
      });
      if (!res.ok) {
        const data = res.data as { detail?: string };
        throw new Error(data.detail ?? "Rename failed");
      }
      setEditing(false);
      onRenamed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col gap-1" data-testid="passkey-rename-form">
        <div className="flex items-center gap-1">
          <input
            data-testid="passkey-name-input"
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={MAX_NAME_LENGTH}
            className="text-sm border rounded px-2 py-0.5 w-48 bg-surface text-text border-border"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
          />
          <button
            data-testid="passkey-name-save"
            onClick={save}
            disabled={saving}
            className="p-1 text-success hover:bg-surface-hover rounded"
            aria-label="Save name"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
          <button
            data-testid="passkey-name-cancel"
            onClick={cancel}
            className="p-1 text-text-muted hover:bg-surface-hover rounded"
            aria-label="Cancel rename"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        {error && (
          <span className="text-xs text-danger block" data-testid="passkey-rename-error">
            {error}
          </span>
        )}
      </div>
    );
  }

  return (
    <span className="inline-flex items-center gap-1">
      <span data-testid="passkey-name">{passkey.name || "Unnamed passkey"}</span>
      {!passkey.revoked_at && (
        <button
          data-testid="passkey-edit-btn"
          onClick={startEdit}
          className="p-0.5 text-text-muted hover:text-text rounded"
          aria-label="Edit passkey name"
        >
          <Pencil className="w-3 h-3" />
        </button>
      )}
    </span>
  );
}

export function Settings() {
  const queryClient = useQueryClient();
  const [addLoading, setAddLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastPasskeyError, setLastPasskeyError] = useState<string | null>(null);
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => readThemePreference());

  const { data: passkeys, isLoading } = useQuery<PasskeyInfo[]>({
    queryKey: ["passkeys"],
    queryFn: async () => {
      const { data, error } = await api.GET("/auth/passkeys");
      if (error) throw new Error("Failed to load passkeys");
      return data.passkeys;
    },
  });

  const revokeMutation = useMutation({
    mutationFn: async (passkeyId: string) => {
      setLastPasskeyError(null);
      const res = await apiFetch(`/auth/passkeys/${passkeyId}/revoke`, {
        method: "POST",
      });
      if (!res.ok) {
        const data = res.data as { error?: string; detail?: string | { code?: string; message?: string } };
        const detail = data.detail;
        if (
          data.error === "LAST_PASSKEY" ||
          (typeof detail === "string" && detail.includes("LAST_PASSKEY")) ||
          (typeof detail === "object" && detail?.code === "LAST_PASSKEY")
        ) {
          throw new Error("LAST_PASSKEY");
        }
        const msg = typeof detail === "string" ? detail : (detail as { message?: string })?.message || "Revoke failed";
        throw new Error(msg);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["passkeys"] });
    },
    onError: (err: Error) => {
      if (err.message === "LAST_PASSKEY") {
        setLastPasskeyError(
          "Cannot revoke your last active passkey. Add another passkey first to maintain account access."
        );
      } else {
        setError(err.message);
      }
    },
  });

  const handleAddPasskey = async () => {
    setAddLoading(true);
    setError(null);
    try {
      const startRes = await apiFetch<{ options: Record<string, unknown>; flow_id: string }>(
        "/auth/passkey/add/start",
        { method: "POST" }
      );
      if (!startRes.ok) throw new Error("Failed to start passkey addition");

      const createOptions = toCreateOptions(
        startRes.data.options as unknown as Parameters<typeof toCreateOptions>[0]
      );
      const credential = (await navigator.credentials.create(
        createOptions
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

      queryClient.invalidateQueries({ queryKey: ["passkeys"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add passkey");
    } finally {
      setAddLoading(false);
    }
  };

  const activePasskeys = passkeys?.filter((p) => !p.revoked_at) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Settings</h1>
        <p className="text-text-muted">Manage your passkeys and account security</p>
      </div>

      {error && <Alert variant="error" data-testid="settings-error">{error}</Alert>}
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
          <h2 className="text-lg font-semibold text-text">Theme</h2>
        </CardHeader>
        <CardContent>
          <fieldset className="space-y-2">
            <legend className="sr-only">Theme preference</legend>
            {(["system", "light", "dark"] as const).map((option) => (
              <label key={option} className="flex items-center gap-2 text-sm text-text">
                <input
                  type="radio"
                  name="theme-preference"
                  value={option}
                  checked={themePreference === option}
                  onChange={() => {
                    setThemePreference(option);
                    applyThemePreference(option);
                  }}
                />
                {option === "system"
                  ? "System"
                  : option === "light" ? "Light" : "Dark"}
              </label>
            ))}
          </fieldset>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Fingerprint className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text">Passkeys</h2>
            <span className="text-sm text-text-muted">({activePasskeys.length} active)</span>
          </div>
          <Button size="sm" onClick={handleAddPasskey} disabled={addLoading} data-testid="add-passkey-btn">
            <Plus className="w-4 h-4" />
            {addLoading ? "Adding..." : "Add Passkey"}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
            </div>
          ) : passkeys && passkeys.length > 0 ? (
            <div className="divide-y divide-border">
              {passkeys.map((passkey) => (
                <div key={passkey.id} className="flex items-center justify-between py-3" data-testid="passkey-item">
                  <div>
                    <div className="text-sm font-medium text-text">
                      <PasskeyName
                        passkey={passkey}
                        onRenamed={() =>
                          queryClient.invalidateQueries({ queryKey: ["passkeys"] })
                        }
                      />
                      {passkey.revoked_at && (
                        <span className="ml-2 text-xs text-danger">(revoked)</span>
                      )}
                    </div>
                    <p className="text-xs text-text-muted font-mono">{passkey.id}</p>
                    <p className="text-xs text-text-muted">
                      Created: {new Date(passkey.created_at).toLocaleDateString()}
                      {passkey.last_used_at && (
                        <> | Last used: {new Date(passkey.last_used_at).toLocaleDateString()}</>
                      )}
                    </p>
                  </div>
                  {!passkey.revoked_at && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => revokeMutation.mutate(passkey.id)}
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
            <p className="text-sm text-text-muted py-4 text-center">No passkeys found.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
