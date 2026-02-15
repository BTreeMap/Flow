import { useState } from "react";
import { Link } from "react-router";
import { Fingerprint, UserPlus } from "lucide-react";
import { useAuth } from "../auth";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { Alert } from "../components/Alert";

export function Register() {
  const { register, isAuthenticated } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuthenticated) {
    return (
      <div className="max-w-md mx-auto py-16 text-center">
        <Alert variant="info">You are already registered and logged in.</Alert>
      </div>
    );
  }

  const handleRegister = async () => {
    if (!displayName.trim()) {
      setError("Please enter a display name");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await register(displayName.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-16">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-xl">
              <UserPlus className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-text">Create Account</h2>
              <p className="text-sm text-text-muted">Register with a passkey</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <Alert variant="error" data-testid="register-error">{error}</Alert>}

          <Input
            label="Display Name"
            placeholder="Enter your name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRegister()}
            data-testid="register-display-name"
          />

          <Button onClick={handleRegister} disabled={loading} className="w-full" data-testid="register-submit">
            <Fingerprint className="w-4 h-4" />
            {loading ? "Creating account..." : "Register with Passkey"}
          </Button>

          <p className="text-center text-sm text-text-muted">
            Already have an account?{" "}
            <Link to="/login" className="text-primary hover:underline">
              Login
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
