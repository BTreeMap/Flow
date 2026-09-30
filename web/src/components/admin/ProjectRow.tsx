import { useState } from "react";
import { Pencil } from "lucide-react";
import { Badge, type BadgeTone } from "../Badge";
import { Button } from "../Button";
import api from "../../api/client";
import type { AdminProjectItem } from "../../api/types";

export function ProjectRow({
    project,
    onUpdated,
}: {
    project: AdminProjectItem;
    onUpdated: () => void;
}) {
    const [editing, setEditing] = useState(false);
    const [name, setName] = useState(project.display_name || "");
    const [status, setStatus] = useState(project.status ?? "active");
    const [saving, setSaving] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [rowError, setRowError] = useState<string | null>(null);

    const save = async (newStatus?: string) => {
        setSaving(true);
        setRowError(null);
        try {
            const body: Record<string, string> = {};
            if (name !== (project.display_name || "")) body.display_name = name;
            if (newStatus && newStatus !== (project.status ?? "active"))
                body.status = newStatus;
            else if (status !== (project.status ?? "active")) body.status = status;

            if (Object.keys(body).length > 0) {
                const { error } = await api.PATCH("/admin/projects/{project_id}", {
                    params: { path: { project_id: project.project_id } },
                    body,
                });
                if (error) throw new Error("Failed to update project");
            }
            setEditing(false);
            setShowConfirm(false);
            onUpdated();
        } catch (err) {
            setRowError(err instanceof Error ? err.message : "Update failed");
        } finally {
            setSaving(false);
        }
    };

    const statusBadge = (s: string) => {
        const tones: Record<string, BadgeTone> = {
            active: "success",
            paused: "warning",
            ended: "danger",
        };
        return <Badge tone={tones[s] ?? "neutral"}>{s}</Badge>;
    };

    if (showConfirm) {
        return (
            <div className="rounded-xl border border-danger/50 p-3 text-sm space-y-2">
                <p className="text-danger font-medium">
                    End project "{project.display_name}"?
                </p>
                <p className="text-text-muted text-xs">
                    This will mark the project as ended. Participants will see it greyed
                    out.
                </p>
                <div className="flex gap-2">
                    <Button
                        variant="danger"
                        size="sm"
                        onClick={() => void save("ended")}
                        disabled={saving}
                    >
                        Confirm End
                    </Button>
                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => { setShowConfirm(false); }}
                    >
                        Cancel
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="rounded-xl border border-border p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
                <div className="flex-1 min-w-0">
                    {editing ? (
                        <div className="flex items-center gap-2">
                            <input
                                type="text"
                                value={name}
                                onChange={(e) => { setName(e.target.value); }}
                                className="text-sm border rounded px-2 py-0.5 flex-1 bg-surface text-text border-border"
                                autoFocus
                            />
                            <select
                                value={status}
                                onChange={(e) => { setStatus(e.target.value); }}
                                className="text-xs border rounded px-1 py-0.5 bg-surface text-text border-border"
                            >
                                <option value="active">active</option>
                                <option value="paused">paused</option>
                            </select>
                            <Button size="sm" onClick={() => void save()} disabled={saving}>
                                {saving ? "…" : "Save"}
                            </Button>
                            <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => {
                                    setEditing(false);
                                    setName(project.display_name || "");
                                    setStatus(project.status ?? "active");
                                }}
                            >
                                Cancel
                            </Button>
                        </div>
                    ) : (
                        <>
                            <p className="font-medium text-text">
                                {project.display_name || project.project_id}
                                <span className="ml-2">
                                    {statusBadge(project.status ?? "active")}
                                </span>
                            </p>
                            <p className="text-text-muted">
                                {project.project_id} · {project.member_count} participants
                            </p>
                        </>
                    )}
                </div>
                {!editing && (project.status ?? "active") !== "ended" && (
                    <div className="flex items-center gap-1 shrink-0">
                        <button
                            onClick={() => { setEditing(true); }}
                            className="p-1 text-text-muted hover:text-text rounded"
                            aria-label="Edit project"
                        >
                            <Pencil className="w-3.5 h-3.5" />
                        </button>
                        <Button
                            variant="danger"
                            size="sm"
                            onClick={() => { setShowConfirm(true); }}
                        >
                            End
                        </Button>
                    </div>
                )}
            </div>
            {rowError && <p className="text-xs text-danger mt-1">{rowError}</p>}
        </div>
    );
}
