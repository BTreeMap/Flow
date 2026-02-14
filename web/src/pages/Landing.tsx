import { Link } from "react-router";
import { Shield, Fingerprint, Zap, Lock } from "lucide-react";
import { useAuth } from "../auth";
import { Button } from "../components/Button";

export function Landing() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="max-w-3xl mx-auto text-center py-16">
      <div className="flex justify-center mb-6">
        <div className="p-4 bg-primary/10 rounded-3xl">
          <Shield className="w-12 h-12 text-primary" />
        </div>
      </div>

      <h1 className="text-4xl sm:text-5xl font-bold text-text mb-4">
        Welcome to <span className="text-primary">{"flow-app"}</span>
      </h1>

      <p className="text-lg text-text-muted mb-8 max-w-xl mx-auto">
        A secure-by-default hackathon starter with passkey authentication,
        device-bound keys, and role-based access control.
      </p>

      <div className="flex justify-center gap-4 mb-16">
        {isAuthenticated ? (
          <Link to="/dashboard">
            <Button size="lg">Go to Dashboard</Button>
          </Link>
        ) : (
          <>
            <Link to="/register">
              <Button size="lg" data-testid="landing-register">
                <Fingerprint className="w-5 h-5" />
                Get Started
              </Button>
            </Link>
            <Link to="/login">
              <Button variant="secondary" size="lg" data-testid="landing-login">
                Login
              </Button>
            </Link>
          </>
        )}
      </div>

      <div className="grid sm:grid-cols-3 gap-6 text-left">
        <div className="p-6 bg-surface-alt rounded-2xl border border-border">
          <Fingerprint className="w-8 h-8 text-primary mb-3" />
          <h3 className="font-semibold text-text mb-1">Passkey Auth</h3>
          <p className="text-sm text-text-muted">
            No passwords. Register and login with device biometrics or security keys.
          </p>
        </div>
        <div className="p-6 bg-surface-alt rounded-2xl border border-border">
          <Lock className="w-8 h-8 text-primary mb-3" />
          <h3 className="font-semibold text-text mb-1">Device-Bound Keys</h3>
          <p className="text-sm text-text-muted">
            Each device has a non-extractable P-256 keypair. Tokens are signed locally and verified server-side.
          </p>
        </div>
        <div className="p-6 bg-surface-alt rounded-2xl border border-border">
          <Zap className="w-8 h-8 text-primary mb-3" />
          <h3 className="font-semibold text-text mb-1">Ship Fast</h3>
          <p className="text-sm text-text-muted">
            Built on FastAPI + React + Vite. Secure defaults so you can focus on building.
          </p>
        </div>
      </div>
    </div>
  );
}
