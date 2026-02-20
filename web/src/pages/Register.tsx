import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router";
import { Fingerprint, Mail, UserPlus, User, ArrowRight } from "lucide-react";
import { useAuth } from "../auth";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { Alert } from "../components/Alert";
import api from "../api/client";

type Step = "email" | "passkey" | "display_name";

function safeReturnTo(value: string | null): string {
  if (!value) return "/dashboard";
  // Only allow relative paths (no external redirects)
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  return "/dashboard";
}

function emailLocalPart(raw: string): string {
  const s = raw.trim();
  const at = s.indexOf("@");
  if (at <= 0) return "";
  return s.slice(0, at);
}

export function Register() {
  const { register, isAuthenticated } = useAuth();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const returnTo = safeReturnTo(searchParams.get("return_to"));

  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuthenticated && step === "email") {
    return (
      <div className="max-w-md mx-auto py-16 text-center">
        <Alert variant="info">You are already registered and logged in.</Alert>
      </div>
    );
  }

  const handleEmailSubmit = () => {
    const trimmed = email.trim();
    if (!trimmed || !trimmed.includes("@")) {
      setError("Please enter a valid email address");
      return;
    }

    const localPart = emailLocalPart(trimmed);
    if (!localPart) {
      setError("Please enter a valid email address");
      return;
    }

    setError(null);
    setDisplayName(localPart);
    setStep("passkey");
  };

  const handlePasskeyEnroll = async () => {
    setLoading(true);
    setError(null);
    try {
      const localPart = emailLocalPart(email);
      if (!localPart) throw new Error("Please enter a valid email address");
      await register(localPart);
      setStep("display_name");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleFinish = async () => {
    setLoading(true);
    setError(null);
    try {
      const emailNorm = email.trim().toLowerCase();
      const fallbackName = emailLocalPart(emailNorm);

      const { error: apiError } = await api.PATCH("/me", {
        body: {
          email: emailNorm,
          display_name: displayName.trim() || fallbackName,
        },
      });
      if (apiError) throw new Error("Failed to save profile");
      navigate(returnTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setLoading(false);
    }
  };

  const stepIndex = step === "email" ? 0 : step === "passkey" ? 1 : 2;

  return (
    <div className="max-w-md mx-auto py-16">
      {/* Stepper indicator */}
      <div className="flex items-center justify-center gap-2 mb-6">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className={`h-2 rounded-full transition-all ${
              i <= stepIndex ? "w-8 bg-primary" : "w-8 bg-border"
            }`}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-xl">
              {step === "email" ? (
                <Mail className="w-5 h-5 text-primary" />
              ) : step === "passkey" ? (
                <Fingerprint className="w-5 h-5 text-primary" />
              ) : (
                <User className="w-5 h-5 text-primary" />
              )}
            </div>
            <div>
              <h2 className="text-xl font-bold text-text">
                {step === "email"
                  ? "Your Email"
                  : step === "passkey"
                    ? "Create Passkey"
                    : "Your Name"}
              </h2>
              <p className="text-sm text-text-muted">
                {step === "email"
                  ? "Step 1 of 3 · Enter your email"
                  : step === "passkey"
                    ? "Step 2 of 3 · Enroll a passkey for login"
                    : "Step 3 of 3 · Set your display name"}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="error" data-testid="register-error">
              {error}
            </Alert>
          )}

          {step === "email" && (
            <>
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleEmailSubmit()}
                data-testid="register-email"
                autoFocus
              />
              <Button
                onClick={handleEmailSubmit}
                disabled={!email.trim()}
                className="w-full"
                data-testid="register-email-submit"
              >
                <ArrowRight className="w-4 h-4" />
                Continue
              </Button>
            </>
          )}

          {step === "passkey" && (
            <>
              <p className="text-sm text-text-muted">
                You'll be prompted to create a passkey for secure, passwordless
                login.
              </p>
              <Button
                onClick={handlePasskeyEnroll}
                disabled={loading}
                className="w-full"
                data-testid="register-submit"
              >
                <Fingerprint className="w-4 h-4" />
                {loading ? "Creating account..." : "Register with Passkey"}
              </Button>
            </>
          )}

          {step === "display_name" && (
            <>
              <Input
                label="Display Name"
                placeholder="Enter your name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleFinish()}
                data-testid="register-display-name"
                autoFocus
              />
              <Button
                onClick={handleFinish}
                disabled={loading || !displayName.trim()}
                className="w-full"
                data-testid="register-finish"
              >
                <UserPlus className="w-4 h-4" />
                {loading ? "Saving..." : "Complete Registration"}
              </Button>
            </>
          )}

          {step === "email" && (
            <p className="text-center text-sm text-text-muted">
              Already have an account?{" "}
              <Link
                to={`/login${returnTo !== "/dashboard" ? `?return_to=${encodeURIComponent(returnTo)}` : ""}`}
                className="text-primary hover:underline"
              >
                Login
              </Link>
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
