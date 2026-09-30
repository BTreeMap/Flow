import { useState } from "react";
import { Check, X, Pencil } from "lucide-react";
import { apiFetch } from "../../auth";
import type { PasskeyInfo } from "../../api/types";

const MAX_NAME_LENGTH = 64;

export function PasskeyName({
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
                        onChange={(e) => { setDraft(e.target.value); }}
                        maxLength={MAX_NAME_LENGTH}
                        className="text-[16px] border rounded px-2 py-0.5 w-48 bg-surface text-text border-border"
                        autoFocus
                        onKeyDown={(e) => {
                            if (e.key === "Enter") void save();
                            if (e.key === "Escape") cancel();
                        }}
                    />
                    <button
                        data-testid="passkey-name-save"
                        onClick={() => void save()}
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
                    <span
                        className="text-xs text-danger block"
                        data-testid="passkey-rename-error"
                    >
                        {error}
                    </span>
                )}
            </div>
        );
    }

    return (
        <span className="inline-flex items-center gap-1">
            <span data-testid="passkey-name">
                {passkey.name || "Unnamed passkey"}
            </span>
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
