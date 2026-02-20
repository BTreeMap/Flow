import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Input } from "../components/Input";
import { getOrMintToken } from "../auth/token";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export function Onboarding() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [promptAnchor, setPromptAnchor] = useState("");
  const [preferredTime, setPreferredTime] = useState("");
  const [habitDomain, setHabitDomain] = useState("");
  const [motivationalFrame, setMotivationalFrame] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptAnchor.trim() || !preferredTime.trim()) {
      setError("Prompt anchor and preferred time are required.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/p/${projectId}/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          prompt_anchor: promptAnchor.trim(),
          preferred_time: preferredTime.trim(),
          habit_domain: habitDomain.trim(),
          motivational_frame: motivationalFrame.trim(),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Onboarding failed (${res.status})`);
      }
      navigate(`/p/${projectId}/chat`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Onboarding failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto">
      <Card>
        <CardHeader>
          <h1 className="text-xl font-bold text-text">Complete onboarding</h1>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <Alert variant="error">{error}</Alert>}
            <Input
              label="Prompt anchor"
              value={promptAnchor}
              onChange={(e) => setPromptAnchor(e.target.value)}
              placeholder="After my morning coffee"
              required
            />
            <Input
              label="Preferred time"
              value={preferredTime}
              onChange={(e) => setPreferredTime(e.target.value)}
              placeholder="08:00 or 8am"
              required
            />
            <Input
              label="Habit domain (optional)"
              value={habitDomain}
              onChange={(e) => setHabitDomain(e.target.value)}
            />
            <Input
              label="Motivational frame (optional)"
              value={motivationalFrame}
              onChange={(e) => setMotivationalFrame(e.target.value)}
            />
            <Button
              type="submit"
              className="w-full"
              disabled={
                submitting || !promptAnchor.trim() || !preferredTime.trim()
              }
            >
              {submitting ? "Saving…" : "Continue to chat"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
