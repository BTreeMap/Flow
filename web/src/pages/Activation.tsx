import { useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { Alert } from "../components/Alert";
import { useAuth } from "../auth";
import api from "../api/client";

export function Activation() {
  const { projectId } = useParams<{ projectId: string }>();
  const [searchParams] = useSearchParams();
  const inviteCode = searchParams.get("invite") || "";
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [email, setEmail] = useState("");
  const [needsEmail, setNeedsEmail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Redirect unauthenticated users to register with return_to
  if (!authLoading && !isAuthenticated) {
    const returnTo = `/p/${projectId}/activate?invite=${encodeURIComponent(inviteCode)}`;
    navigate(`/register?return_to=${encodeURIComponent(returnTo)}`, {
      replace: true,
    });
    return null;
  }

  const doClaim = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const { error: apiError, response } = await api.POST(
        "/p/{project_id}/activate/claim",
        {
          params: { path: { project_id: projectId! } },
          body: { invite_code: inviteCode },
        },
      );

      if (response.status === 409) {
        // Check for EMAIL_REQUIRED
        const body = apiError as unknown as { code?: string; message?: string };
        if (body?.code === "EMAIL_REQUIRED") {
          setNeedsEmail(true);
          setSubmitting(false);
          return;
        }
      }

      if (apiError) {
        const detail =
          typeof apiError === "object" &&
          apiError !== null &&
          "detail" in apiError
            ? (apiError as { detail?: string }).detail
            : undefined;
        throw new Error(detail || `Activation failed (${response.status})`);
      }

      navigate(`/p/${projectId}/onboarding/notifications`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      setError("Email is required");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      // Save email via PATCH /me
      const { error: patchError } = await api.PATCH("/me", {
        body: { email: trimmed },
      });
      if (patchError) throw new Error("Failed to save email");

      // Retry claim
      setNeedsEmail(false);
      await doClaim();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save email");
      setSubmitting(false);
    }
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    await doClaim();
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
          {error && <Alert variant="error">{error}</Alert>}

          {!inviteCode && (
            <Alert variant="warning">
              No invite code found. Please use the invite link you received.
            </Alert>
          )}

          {needsEmail ? (
            <form onSubmit={handleEmailSubmit} className="space-y-4">
              <Alert variant="info">
                Add your email to continue joining this project.
              </Alert>
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
              <Button
                type="submit"
                disabled={submitting || !email.trim()}
                className="w-full"
              >
                {submitting ? "Saving…" : "Save & Continue"}
              </Button>
            </form>
          ) : (
            <form onSubmit={handleJoin} className="space-y-4">
              <Button
                type="submit"
                disabled={submitting || !inviteCode}
                className="w-full"
              >
                {submitting ? "Joining…" : "Join Project"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
