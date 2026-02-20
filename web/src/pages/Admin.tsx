import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { getOrMintToken } from "../auth/token";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Input } from "../components/Input";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface ProjectItem {
  project_id: string;
  display_name: string | null;
  created_at: string;
  member_count: number;
}

interface DebugCheck {
  key: string;
  ok: boolean;
  detail: string;
}

interface DebugStatus {
  llm_mode: string;
  checks: DebugCheck[];
}

interface LlmConnectivityResult {
  ok: boolean;
  model: string;
  latency_ms: number;
  output?: string | null;
  error?: string | null;
}

export function Admin() {
  const { role } = useAuth();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [inviteProjectId, setInviteProjectId] = useState("");
  const [inviteCount, setInviteCount] = useState("1");
  const [inviteMaxUses, setInviteMaxUses] = useState("");
  const [inviteCodes, setInviteCodes] = useState<string[]>([]);
  const [debugStatus, setDebugStatus] = useState<DebugStatus | null>(null);
  const [llmTest, setLlmTest] = useState<LlmConnectivityResult | null>(null);
  const [runningLlmTest, setRunningLlmTest] = useState(false);
  const [expiresAt, setExpiresAt] = useState(
    new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16),
  );

  const loadProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/admin/projects`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load projects (${res.status})`);
      const data = (await res.json()) as { projects: ProjectItem[] };
      setProjects(data.projects || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  };

  const loadDebugStatus = async () => {
    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/admin/debug/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load debug status (${res.status})`);
      setDebugStatus((await res.json()) as DebugStatus);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load debug status",
      );
    }
  };

  useEffect(() => {
    void loadProjects();
    void loadDebugStatus();
  }, []);

  const createProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) return;
    setError(null);
    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/admin/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ display_name: displayName.trim() }),
      });
      if (!res.ok) throw new Error(`Failed to create project (${res.status})`);
      setDisplayName("");
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    }
  };

  const createInvites = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteProjectId.trim()) return;
    setError(null);
    try {
      const token = await getOrMintToken("http");
      const count = Number.parseInt(inviteCount, 10) || 1;
      const maxUses = Number.parseInt(inviteMaxUses, 10);
      const res = await fetch(
        `${API_BASE}/admin/projects/${inviteProjectId}/invites`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            count,
            expires_at: new Date(expiresAt).toISOString(),
            max_uses: Number.isFinite(maxUses) ? maxUses : null,
          }),
        },
      );
      if (!res.ok) throw new Error(`Failed to create invites (${res.status})`);
      const data = (await res.json()) as { invite_codes: string[] };
      setInviteCodes(
        (data.invite_codes || []).map(
          (code) => `${window.location.origin}/p/${inviteProjectId}/activate?invite=${code}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invites");
    }
  };

  const copyAllInvites = async () => {
    if (!inviteCodes.length) return;
    await navigator.clipboard.writeText(inviteCodes.join("\n"));
  };

  const runLlmConnectivityTest = async () => {
    setRunningLlmTest(true);
    setError(null);
    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/admin/debug/llm-connectivity`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`LLM test failed (${res.status})`);
      setLlmTest((await res.json()) as LlmConnectivityResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run LLM test");
    } finally {
      setRunningLlmTest(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Admin Panel</h1>
        <p className="text-text-muted">Server-side RBAC enforces all operations</p>
      </div>

      {error && <Alert variant="error">{error}</Alert>}
      {role !== "admin" && <Alert variant="warning">Admin role required.</Alert>}

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-text">Debug diagnostics</h2>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            <p className="text-text-muted">
              LLM mode:{" "}
              <span className="font-medium text-text">
                {debugStatus?.llm_mode ?? "loading"}
              </span>
            </p>
            {debugStatus?.checks.map((check) => (
              <p key={check.key} className="text-text-muted">
                <span className={check.ok ? "text-success" : "text-danger"}>
                  {check.ok ? "✓" : "✗"}
                </span>{" "}
                <span className="font-medium text-text">{check.key}</span> —{" "}
                {check.detail}
              </p>
            ))}
            <div className="pt-2">
              <Button onClick={() => void runLlmConnectivityTest()} disabled={runningLlmTest}>
                {runningLlmTest ? "Testing..." : "Run LLM connectivity test"}
              </Button>
            </div>
            {llmTest && (
              <pre className="text-xs bg-surface-alt p-3 rounded-xl overflow-auto">
                {JSON.stringify(llmTest, null, 2)}
              </pre>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-text">Create project</h2>
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
              Create project
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold text-text">Generate invites</h2>
        </CardHeader>
        <CardContent>
          <form onSubmit={createInvites} className="space-y-3">
            <Input
              label="Project ID"
              value={inviteProjectId}
              onChange={(e) => setInviteProjectId(e.target.value)}
              required
            />
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
            <p className="text-xs text-text-muted -mt-2">
              Leave empty for unlimited uses (recommended for WhatsApp groups).
            </p>
            <Input
              label="Expires at"
              type="datetime-local"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              required
            />
            <Button type="submit">Generate invites</Button>
          </form>
          {inviteCodes.length > 0 && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-text">Invite links</p>
                <Button onClick={() => void copyAllInvites()}>Copy all</Button>
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
          <h2 className="text-lg font-semibold text-text">Projects</h2>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-text-muted">Loading…</p>
          ) : (
            <div className="space-y-2">
              {projects.map((project) => (
                <div
                  key={project.project_id}
                  className="rounded-xl border border-border p-3 text-sm"
                >
                  <p className="font-medium text-text">
                    {project.display_name || project.project_id}
                  </p>
                  <p className="text-text-muted">
                    {project.project_id} · {project.member_count} participants
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
