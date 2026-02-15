import { useAuth } from "../auth";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "../components/Card";
import { Alert } from "../components/Alert";
import { MessageSquare } from "lucide-react";
import { Link } from "react-router";
import { getOrMintToken } from "../auth/token";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

interface Membership {
  project_id: string;
  display_name: string;
  status: string;
}

interface DashboardData {
  memberships: Membership[];
}

export function Dashboard() {
  const { displayName } = useAuth();

  const { data, isLoading, error } = useQuery<DashboardData>({
    queryKey: ["dashboard"],
    queryFn: async () => {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load dashboard (${res.status})`);
      return res.json();
    },
  });

  const { data: pingData } = useQuery<{ ok: boolean }>({
    queryKey: ["demo-ping"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/demo/ping`);
      return res.json();
    },
  });

  const { data: echoData } = useQuery<{ message: string; reversed: string }>({
    queryKey: ["demo-echo"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/demo/echo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "hello" }),
      });
      return res.json();
    },
  });

  const memberships = data?.memberships || [];
  const active = memberships.filter((m) => m.status === "active");
  const ended = memberships.filter((m) => m.status !== "active");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text" data-testid="dashboard-heading">Dashboard</h1>
        <p className="text-text-muted">
          Welcome{displayName ? `, ${displayName}` : ""}!
        </p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
        </div>
      )}

      {error && (
        <Alert variant="error">
          {error instanceof Error ? error.message : "Failed to load projects"}
        </Alert>
      )}

      {!isLoading && memberships.length === 0 && !error && (
        <Card>
          <CardContent className="py-12 text-center text-text-muted">
            <MessageSquare className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>No projects yet.</p>
            <p className="text-sm mt-1">Use an invite link to join a research project.</p>
          </CardContent>
        </Card>
      )}

      {active.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wide">Active Projects</h2>
          <div className="grid gap-3">
            {active.map((m) => (
              <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
                <Card className="hover:border-primary/40 transition-colors cursor-pointer">
                  <CardContent className="flex items-center gap-3 py-4">
                    <div className="p-2 bg-primary/10 rounded-xl">
                      <MessageSquare className="w-5 h-5 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-text truncate">{m.display_name}</p>
                      <p className="text-xs text-text-muted capitalize">{m.status}</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}

      {ended.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wide">Ended</h2>
          <div className="grid gap-3 opacity-60">
            {ended.map((m) => (
              <Link key={m.project_id} to={`/p/${m.project_id}/chat`}>
                <Card className="cursor-pointer">
                  <CardContent className="flex items-center gap-3 py-4">
                    <div className="p-2 bg-surface-alt rounded-xl">
                      <MessageSquare className="w-5 h-5 text-text-muted" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-text truncate">{m.display_name}</p>
                      <p className="text-xs text-text-muted capitalize">{m.status}</p>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2 text-sm text-text-muted">
        <p data-testid="demo-ping">
          {pingData ? `✓ ${pingData.ok ? "ok" : "fail"}` : "…"}
        </p>
        <p data-testid="demo-echo">
          {echoData
            ? `"${echoData.message}" → "${echoData.reversed}"`
            : "…"}
        </p>
      </div>
    </div>
  );
}
