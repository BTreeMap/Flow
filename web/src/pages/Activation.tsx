import { useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { Alert } from "../components/Alert";
import { getOrMintToken } from "../auth/token";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export function Activation() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams] = useSearchParams();
  const inviteCode = searchParams.get("invite") || "";
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/p/${projectId}/activate/claim`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          invite_code: inviteCode,
          email: email || undefined,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Activation failed (${res.status})`);
      }

      navigate(`/p/${projectId}/chat`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-md mx-auto">
      <Card>
        <CardHeader>
          <h1 className="text-xl font-bold text-text">Join Project</h1>
          <p className="text-sm text-text-muted mt-1">
            You've been invited to join a research project.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <Alert variant="error">{error}</Alert>}

            {!inviteCode && (
              <Alert variant="warning">
                No invite code found. Please use the invite link you received.
              </Alert>
            )}

            <Input
              label="Email (optional)"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <p className="text-xs text-text-muted -mt-2">
              Optional contact info only — not used for login or identity.
            </p>

            <Button
              type="submit"
              disabled={submitting || !inviteCode}
              className="w-full"
            >
              {submitting ? "Joining…" : "Join Project"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
