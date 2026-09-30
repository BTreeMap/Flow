import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Beaker,
  Bug,
  ClipboardCopy,
  FolderPlus,
  Send,
  TicketPlus,
} from "lucide-react";
import { useAuth } from "../auth";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Input } from "../components/Input";
import { SectionHeader } from "../components/SectionHeader";
import { ProjectRow } from "../components/admin/ProjectRow";
import { PushTestPanel } from "../components/admin/PushTestPanel";
import api from "../api/client";
import type {
  AdminCreateInvitesResponse,
  AdminDebugStatusResponse,
  AdminLLMConnectivityRequest,
  AdminLLMConnectivityResponse,
  AdminProjectsResponse,
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

  const projectsQuery = useQuery<AdminProjectsResponse["projects"]>({
    queryKey: ["admin-projects"],
    queryFn: async () => {
      const { data, error: apiError } = await api.GET("/admin/projects");
      if (apiError) {
        throw new Error(readErrorMessage(apiError, "Failed to load projects"));
      }
      return data.projects ?? [];
    },
  });
  const debugQuery = useQuery<AdminDebugStatusResponse>({
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

  const createProject = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!displayName.trim()) return;
    setError(null);
    await createProjectMutation.mutateAsync(displayName.trim());
    setDisplayName("");
  };

  const createInvites = async (e: React.SyntheticEvent) => {
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
      void queryClient.invalidateQueries({ queryKey: ["admin-projects"] });
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
        <h1 className="display-sm text-text">Admin Panel</h1>
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
              onChange={(e) => { setLlmModel(e.target.value); }}
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
              onChange={(e) => { setLlmMaxTokens(e.target.value); }}
            />
            <Input
              label="Temperature"
              value={llmTemperature}
              type="number"
              step="0.1"
              min={0}
              max={2}
              onChange={(e) => { setLlmTemperature(e.target.value); }}
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
              onChange={(e) => { setLlmPrompt(e.target.value); }}
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
          <form onSubmit={(e) => void createProject(e)} className="space-y-3">
            <Input
              label="Display name"
              value={displayName}
              onChange={(e) => { setDisplayName(e.target.value); }}
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
          <form onSubmit={(e) => void createInvites(e)} className="space-y-3">
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
                onChange={(e) => { setInviteProjectId(e.target.value); }}
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
              onChange={(e) => { setInviteCount(e.target.value); }}
            />
            <Input
              label="Max uses per invite"
              type="number"
              min={1}
              placeholder="Unlimited"
              value={inviteMaxUses}
              onChange={(e) => { setInviteMaxUses(e.target.value); }}
            />
            <Input
              label="Expires at"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => { setExpiresAt(e.target.value); }}
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
                    void queryClient.invalidateQueries({
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

