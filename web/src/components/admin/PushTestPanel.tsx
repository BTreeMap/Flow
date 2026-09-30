import { useState } from "react";
import { Bell, Send } from "lucide-react";
import { Alert } from "../Alert";
import { Button } from "../Button";
import { Card, CardContent, CardHeader } from "../Card";
import { Input } from "../Input";
import { SectionHeader } from "../SectionHeader";
import api from "../../api/client";
import type {
    AdminProjectItem,
    AdminPushChannelItem,
    AdminPushTestResultItem,
} from "../../api/types";

export function PushTestPanel({ projects }: { projects: AdminProjectItem[] }) {
    const [selectedProject, setSelectedProject] = useState("");
    const [channels, setChannels] = useState<AdminPushChannelItem[]>([]);
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [title, setTitle] = useState("Test notification");
    const [body, setBody] = useState("This is a test push from Flow admin.");
    const [url, setUrl] = useState("");
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState<AdminPushTestResultItem[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [filter, setFilter] = useState("");

    const loadChannels = async (projectId: string) => {
        setSelectedProject(projectId);
        setChannels([]);
        setSelectedIds(new Set());
        setResults([]);
        if (!projectId) return;
        try {
            const { data, error: apiError } = await api.GET(
                "/admin/projects/{project_id}/push/channels",
                { params: { path: { project_id: projectId } } },
            );
            if (apiError) throw new Error("Failed to load channels");
            setChannels(data.channels ?? []);
        } catch (err) {
            setError(
                err instanceof Error ? err.message : "Failed to load push channels",
            );
        }
    };

    const toggleId = (id: number) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const selectAll = () => {
        setSelectedIds(new Set(filteredChannels.map((c) => c.subscription_id)));
    };

    const filteredChannels = channels.filter((c) => {
        if (!filter) return true;
        const q = filter.toLowerCase();
        return (
            (c.user_email ?? "").toLowerCase().includes(q) ||
            (c.display_name ?? "").toLowerCase().includes(q)
        );
    });

    const sendTest = async () => {
        if (!selectedProject || selectedIds.size === 0) return;
        setLoading(true);
        setError(null);
        setResults([]);
        try {
            const { data, error: apiError } = await api.POST("/admin/push/test", {
                body: {
                    project_id: selectedProject,
                    subscription_ids: Array.from(selectedIds),
                    title,
                    body,
                    url: url || undefined,
                },
            });
            if (apiError) throw new Error("Push test failed");
            setResults(data.results ?? []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Push test failed");
        } finally {
            setLoading(false);
        }
    };

    const activeProjects = projects.filter(
        (p) => (p.status ?? "active") === "active",
    );

    return (
        <Card>
            <CardHeader>
                <SectionHeader
                    icon={<Bell className="w-5 h-5" />}
                    title="Push test"
                    subtitle="Send test notifications to selected devices"
                />
            </CardHeader>
            <CardContent className="space-y-3">
                {error && <Alert variant="error">{error}</Alert>}
                <div className="space-y-1.5">
                    <label
                        className="block text-sm font-medium text-text"
                        htmlFor="push-project"
                    >
                        Project
                    </label>
                    <select
                        id="push-project"
                        value={selectedProject}
                        onChange={(e) => void loadChannels(e.target.value)}
                        className="w-full px-3 py-2 bg-surface border border-border rounded-xl text-text focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                    >
                        <option value="">Select a project…</option>
                        {activeProjects.map((p) => (
                            <option key={p.project_id} value={p.project_id}>
                                {p.display_name || p.project_id}
                            </option>
                        ))}
                    </select>
                </div>

                {channels.length > 0 && (
                    <>
                        <div className="flex items-center gap-2">
                            <Input
                                placeholder="Filter by email/name…"
                                value={filter}
                                onChange={(e) => { setFilter(e.target.value); }}
                            />
                            <Button size="sm" variant="secondary" onClick={selectAll}>
                                Select all
                            </Button>
                        </div>
                        <div className="max-h-48 overflow-y-auto divide-y divide-border border border-border rounded-xl">
                            {filteredChannels.map((ch) => (
                                <label
                                    key={ch.subscription_id}
                                    className="flex items-center gap-2 px-3 py-2 hover:bg-surface-alt cursor-pointer text-sm"
                                >
                                    <input
                                        type="checkbox"
                                        checked={selectedIds.has(ch.subscription_id)}
                                        onChange={() => { toggleId(ch.subscription_id); }}
                                    />
                                    <div className="flex-1 min-w-0">
                                        <span className="text-text">
                                            {ch.display_name || ch.user_email || ch.user_id}
                                        </span>
                                        {ch.user_email && ch.display_name && (
                                            <span className="text-text-muted ml-1 text-xs">
                                                ({ch.user_email})
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-xs text-text-muted truncate max-w-32">
                                        {ch.endpoint_hint}
                                    </span>
                                </label>
                            ))}
                        </div>
                    </>
                )}

                <Input
                    label="Title"
                    value={title}
                    onChange={(e) => { setTitle(e.target.value); }}
                />
                <div className="space-y-1.5">
                    <label
                        className="block text-sm font-medium text-text"
                        htmlFor="push-body"
                    >
                        Body
                    </label>
                    <textarea
                        id="push-body"
                        rows={2}
                        value={body}
                        onChange={(e) => { setBody(e.target.value); }}
                        className="w-full px-3 py-2 bg-surface border border-border rounded-xl text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                    />
                </div>
                <Input
                    label="URL (optional)"
                    value={url}
                    onChange={(e) => { setUrl(e.target.value); }}
                    placeholder="/p/.../chat"
                />

                <Button
                    onClick={() => void sendTest()}
                    disabled={
                        loading || selectedIds.size === 0 || !title.trim() || !body.trim()
                    }
                >
                    <Send className="w-4 h-4" />
                    {loading
                        ? "Sending…"
                        : `Send to ${selectedIds.size} device${selectedIds.size !== 1 ? "s" : ""}`}
                </Button>

                {results.length > 0 && (
                    <div className="space-y-1">
                        <p className="text-sm font-medium text-text">Results</p>
                        {results.map((r) => (
                            <div
                                key={r.subscription_id}
                                className={`text-xs px-3 py-1.5 rounded-lg ${r.ok ? "bg-success/10 text-success" : "bg-danger/10 text-danger"}`}
                            >
                                #{r.subscription_id}:{" "}
                                {r.ok ? "✓ sent" : `✗ ${r.error ?? "failed"}`}
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
