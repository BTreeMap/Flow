import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Beaker,
  Bell,
  Bug,
  ClipboardCopy,
  FolderPlus,
  Pencil,
  Send,
  TicketPlus,
} from "lucide-react";
import { useAuth } from "../auth";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Input } from "../components/Input";
import { SectionHeader } from "../components/SectionHeader";
import api from "../api/client";
import type {
  AdminCreateInvitesResponse,
  AdminDebugStatusResponse,
  AdminLLMConnectivityRequest,
  AdminLLMConnectivityResponse,
  AdminProjectItem,
  AdminProjectsResponse,
  AdminPushChannelItem,
  AdminPushTestResultItem,
} from "../api/types";

const MODEL_OPTIONS = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"];

function readErrorMessage(error: unknown, fallback: string): string {
  if (
    error &&
    typeof error === "object" &&
    "detail" in error &&
    typeof (error as { detail?: unknown }).detail === "string"
  ) {
    return (error as { detail: string }).detail;
  }
  return fallback;
}

export function Admin() {
  const queryClient = useQueryClient();
  const { role } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [inviteProjectId, setInviteProjectId] = useState("");
  const [inviteCount, setInviteCount] = useState("1");
  const [inviteMaxUses, setInviteMaxUses] = useState("");
  const [inviteCodes, setInviteCodes] = useState<string[]>([]);
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [llmPrompt, setLlmPrompt] = useState("Reply with exactly: OK");
  const [llmMaxTokens, setLlmMaxTokens] = useState("128");
  const [llmTemperature, setLlmTemperature] = useState("0");
  const [llmResult, setLlmResult] =
    useState<AdminLLMConnectivityResponse | null>(null);
  const [runningLlmTest, setRunningLlmTest] = useState(false);
  const [expiresAt, setExpiresAt] = useState(() =>
    new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16),
  );

  const projectsQuery = useQuery<AdminProjectsResponse["projects"], Error>({
    queryKey: ["admin-projects"],
    queryFn: async () => {
      const { data, error: apiError } = await api.GET("/admin/projects");
      if (apiError) {
        throw new Error(readErrorMessage(apiError, "Failed to load projects"));
      }
      return data.projects ?? [];
    },
  });
  const debugQuery = useQuery<AdminDebugStatusResponse, Error>({
    queryKey: ["admin-debug-status"],
    queryFn: async () => {
      const { data, error: apiError } = await api.GET("/admin/debug/status");
      if (apiError) {
        throw new Error(
          readErrorMessage(apiError, "Failed to load debug status"),
        );
      }
      return data;
    },
  });

  const resolvedError =
    error ?? projectsQuery.error?.message ?? debugQuery.error?.message ?? null;

  const createProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) return;
    setError(null);
    await createProjectMutation.mutateAsync(displayName.trim());
    setDisplayName("");
  };

  const createInvites = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteProjectId.trim()) return;
    setError(null);
    const count = Number.parseInt(inviteCount, 10) || 1;
    const maxUses = Number.parseInt(inviteMaxUses, 10);
    const payload = await createInvitesMutation.mutateAsync({
      projectId: inviteProjectId.trim(),
      count,
      expiresAt,
      maxUses: Number.isFinite(maxUses) ? maxUses : null,
    });
    setInviteCodes(
      (payload.invite_codes ?? []).map(
        (code) =>
          `${window.location.origin}/p/${inviteProjectId}/activate?invite=${code}`,
      ),
    );
  };

  const runLlmConnectivityTest = async () => {
    setRunningLlmTest(true);
    setError(null);
    setLlmResult(null);
    const requestBody: AdminLLMConnectivityRequest = {
      model: llmModel.trim(),
      prompt: llmPrompt,
      max_tokens: Number.parseInt(llmMaxTokens, 10) || 128,
      temperature: Number.parseFloat(llmTemperature) || 0,
    };
    try {
      const data = await llmProbeMutation.mutateAsync(requestBody);
      setLlmResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run LLM probe");
    }
    setRunningLlmTest(false);
  };

  const createProjectMutation = useMutation({
    mutationFn: async (trimmedName: string) => {
      const { error: apiError } = await api.POST("/admin/projects", {
        body: { display_name: trimmedName },
      });
      if (apiError) {
        throw new Error(readErrorMessage(apiError, "Failed to create project"));
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-projects"] });
    },
  });
  const createInvitesMutation = useMutation({
    mutationFn: async ({
      projectId,
      count,
      expiresAt,
      maxUses,
    }: {
      projectId: string;
      count: number;
      expiresAt: string;
      maxUses: number | null;
    }) => {
      const { data, error: apiError } = await api.POST(
        "/admin/projects/{project_id}/invites",
        {
          params: { path: { project_id: projectId } },
          body: {
            count,
            expires_at: new Date(expiresAt).toISOString(),
            max_uses: maxUses,
          },
        },
      );
      if (apiError) {
        throw new Error(readErrorMessage(apiError, "Failed to create invites"));
      }
      return data as AdminCreateInvitesResponse;
    },
  });
  const llmProbeMutation = useMutation({
    mutationFn: async (body: AdminLLMConnectivityRequest) => {
      const { data, error: apiError } = await api.POST(
        "/admin/debug/llm-connectivity",
        {
          body,
        },
      );
      if (apiError) {
        throw new Error(readErrorMessage(apiError, "Failed to run LLM probe"));
      }
      return data as AdminLLMConnectivityResponse;
    },
  });

  const copyAllInvites = async () => {
    if (!inviteCodes.length) return;
    await navigator.clipboard.writeText(inviteCodes.join("\n"));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Admin Panel</h1>
        <p className="text-text-muted">
          Server-side RBAC enforces all operations
        </p>
      </div>

      {resolvedError && <Alert variant="error">{resolvedError}</Alert>}
      {role !== "admin" && (
        <Alert variant="warning">Admin role required.</Alert>
      )}

      <Card>
        <CardHeader>
          <SectionHeader
            icon={<Bug className="w-5 h-5" />}
            title="Debug diagnostics"
            subtitle="Configuration checks and LLM probing"
          />
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-text-muted">
            LLM mode:{" "}
            <span className="font-medium text-text">
              {debugQuery.data?.llm_mode ?? "loading"}
            </span>
          </p>
          {debugQuery.data && (
            <div className="text-sm text-text-muted space-y-1">
              <p>
                OpenAI API key:{" "}
                <span
                  className={
                    debugQuery.data.openai_api_key_configured
                      ? "text-success"
                      : "text-danger"
                  }
                >
                  {debugQuery.data.openai_api_key_configured
                    ? "configured"
                    : "missing"}
                </span>
              </p>
              <p>
                VAPID public key:{" "}
                <span
                  className={
                    debugQuery.data.vapid_public_key_configured
                      ? "text-success"
                      : "text-danger"
                  }
                >
                  {debugQuery.data.vapid_public_key_configured
                    ? "configured"
                    : "missing"}
                </span>
              </p>
              <p>
                VAPID private key:{" "}
                <span
                  className={
                    debugQuery.data.vapid_private_key_configured
                      ? "text-success"
                      : "text-danger"
                  }
                >
                  {debugQuery.data.vapid_private_key_configured
                    ? "configured"
                    : "missing"}
                </span>
              </p>
            </div>
          )}
          {!!debugQuery.data?.warnings.length && (
            <Alert variant="warning">
              <div className="space-y-1">
                {debugQuery.data.warnings.map((warning) => (
                  <p key={warning} className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>{warning}</span>
                  </p>
                ))}
              </div>
            </Alert>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <Input
              label="Model"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              list="admin-llm-model-options"
            />
            <datalist id="admin-llm-model-options">
              {MODEL_OPTIONS.map((model) => (
                <option value={model} key={model} />
              ))}
            </datalist>
            <Input
              label="Max tokens"
              value={llmMaxTokens}
              type="number"
              min={1}
              onChange={(e) => setLlmMaxTokens(e.target.value)}
            />
            <Input
              label="Temperature"
              value={llmTemperature}
              type="number"
              step="0.1"
              min={0}
              max={2}
              onChange={(e) => setLlmTemperature(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label
              className="block text-sm font-medium text-text"
              htmlFor="llm-prompt"
            >
              Prompt
            </label>
            <textarea
              id="llm-prompt"
              rows={3}
              value={llmPrompt}
              onChange={(e) => setLlmPrompt(e.target.value)}
              placeholder="Prompt used for connectivity probe"
              className="w-full px-3 py-2 bg-surface border border-border rounded-xl text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
            />
          </div>
          <Button
            onClick={() => void runLlmConnectivityTest()}
            disabled={runningLlmTest || !llmModel.trim() || !llmPrompt.trim()}
            aria-busy={runningLlmTest}
          >
            <Beaker className="w-4 h-4" />
            {runningLlmTest ? "Testing..." : "Run test"}
          </Button>
          {llmResult && (
            <div className="text-sm space-y-1 bg-surface-alt rounded-xl p-3">
              <p className="text-text">
                {llmResult.ok ? "Probe succeeded" : "Probe failed"} ·{" "}
                {llmResult.latency_ms}ms
              </p>
              {llmResult.response_text && (
                <pre className="text-xs overflow-auto text-text-muted">
                  {llmResult.response_text}
                </pre>
              )}
              {llmResult.error && (
                <p className="text-xs text-danger break-words">
                  {llmResult.error}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader
            icon={<FolderPlus className="w-5 h-5" />}
            title="Create project"
          />
        </CardHeader>
        <CardContent>
          <form onSubmit={createProject} className="space-y-3">
            <Input
              label="Display name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
            />
            <Button type="submit" disabled={!displayName.trim()}>
              <Send className="w-4 h-4" />
              Create project
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader
            icon={<TicketPlus className="w-5 h-5" />}
            title="Generate invites"
          />
        </CardHeader>
        <CardContent>
          <form onSubmit={createInvites} className="space-y-3">
            <div className="space-y-1.5">
              <label
                className="block text-sm font-medium text-text"
                htmlFor="invite-project"
              >
                Project
              </label>
              <select
                id="invite-project"
                value={inviteProjectId}
                onChange={(e) => setInviteProjectId(e.target.value)}
                className="w-full px-3 py-2 bg-surface border border-border rounded-xl text-text focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                required
              >
                <option value="">Select a project…</option>
                {(projectsQuery.data ?? [])
                  .filter((p) => (p.status ?? "active") === "active")
                  .map((p) => (
                    <option key={p.project_id} value={p.project_id}>
                      {p.display_name || p.project_id}
                    </option>
                  ))}
              </select>
            </div>
            <Input
              label="Invite count"
              type="number"
              min={1}
              value={inviteCount}
              onChange={(e) => setInviteCount(e.target.value)}
            />
            <Input
              label="Max uses per invite"
              type="number"
              min={1}
              placeholder="Unlimited"
              value={inviteMaxUses}
              onChange={(e) => setInviteMaxUses(e.target.value)}
            />
            <Input
              label="Expires at"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              required
            />
            <Button type="submit" disabled={!inviteProjectId}>
              <Send className="w-4 h-4" />
              Generate invites
            </Button>
          </form>
          {inviteCodes.length > 0 && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-text">Invite links</p>
                <Button onClick={() => void copyAllInvites()}>
                  <ClipboardCopy className="w-4 h-4" />
                  Copy all
                </Button>
              </div>
              <pre className="text-xs bg-surface-alt p-3 rounded-xl overflow-auto">
                {inviteCodes.join("\n")}
              </pre>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader
            icon={<FolderPlus className="w-5 h-5" />}
            title="Projects"
            subtitle="Manage research projects"
          />
        </CardHeader>
        <CardContent className="space-y-4">
          {projectsQuery.isLoading ? (
            <p className="text-sm text-text-muted">Loading…</p>
          ) : (
            <div className="space-y-2">
              {(projectsQuery.data ?? []).map((project) => (
                <ProjectRow
                  key={project.project_id}
                  project={project}
                  onUpdated={() =>
                    queryClient.invalidateQueries({
                      queryKey: ["admin-projects"],
                    })
                  }
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <PushTestPanel projects={projectsQuery.data ?? []} />
    </div>
  );
}

function ProjectRow({
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
    const colors: Record<string, string> = {
      active: "bg-success/10 text-success",
      paused: "bg-warning/10 text-warning",
      ended: "bg-danger/10 text-danger",
    };
    return (
      <span
        className={`text-xs px-2 py-0.5 rounded-full ${colors[s] || "bg-border text-text-muted"}`}
      >
        {s}
      </span>
    );
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
            onClick={() => setShowConfirm(false)}
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
                onChange={(e) => setName(e.target.value)}
                className="text-sm border rounded px-2 py-0.5 flex-1 bg-surface text-text border-border"
                autoFocus
              />
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
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
              onClick={() => setEditing(true)}
              className="p-1 text-text-muted hover:text-text rounded"
              aria-label="Edit project"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setShowConfirm(true)}
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

function PushTestPanel({ projects }: { projects: AdminProjectItem[] }) {
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
                onChange={(e) => setFilter(e.target.value)}
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
                    onChange={() => toggleId(ch.subscription_id)}
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
          onChange={(e) => setTitle(e.target.value)}
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
            onChange={(e) => setBody(e.target.value)}
            className="w-full px-3 py-2 bg-surface border border-border rounded-xl text-text placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
          />
        </div>
        <Input
          label="URL (optional)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
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
