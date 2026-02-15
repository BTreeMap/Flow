import { useState } from "react";
import { Link } from "react-router";
import { Fingerprint, LogIn } from "lucide-react";
import { useAuth } from "../auth";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";

export function Login() {
  const { login, isAuthenticated } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuthenticated) {
    return (
      <div className="max-w-md mx-auto py-16 text-center">
        <Alert variant="info">You are already logged in.</Alert>
      </div>
    );
  }

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      await login();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
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
              <LogIn className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-text">Welcome Back</h2>
              <p className="text-sm text-text-muted">Login with your passkey</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <Alert variant="error" data-testid="login-error">{error}</Alert>}

          <Button onClick={handleLogin} disabled={loading} className="w-full" data-testid="login-submit">
            <Fingerprint className="w-4 h-4" />
            {loading ? "Authenticating..." : "Login with Passkey"}
          </Button>

          <p className="text-center text-sm text-text-muted">
            No account?{" "}
            <Link to="/register" className="text-primary hover:underline">
              Register
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
