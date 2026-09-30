import { Link } from "react-router";
import { Shield } from "lucide-react";
import { useAuth } from "../auth";
import { Button } from "../components/Button";

export function Landing() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="max-w-2xl mx-auto text-center py-20 px-4">
      <div className="flex justify-center mb-8">
        <div className="relative p-5 rounded-xl bg-gradient-to-br from-primary/15 to-accent/10 ring-1 ring-inset ring-primary/15 shadow-md">
          <Shield className="w-12 h-12 text-primary" />
          <span className="absolute inset-0 rounded-xl bg-primary/5 blur-2xl -z-10" />
        </div>
      </div>

      <p className="text-sm font-medium uppercase tracking-[0.14em] text-text-subtle mb-3">
        HCI Research Platform
      </p>

      <h1 className="display-lg sm:display-xl text-text mb-5">
        Welcome to{" "}
        <span className="bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
          Flow
        </span>
      </h1>

      <p className="text-lg leading-relaxed text-text-muted mb-10 max-w-xl mx-auto">
        Project-based coaching chats with passkey login, real-time conversation
        updates, and optional notifications — built for longitudinal research.
      </p>

      <div className="flex flex-col sm:flex-row justify-center gap-3 mb-16">
        {isAuthenticated ? (
          <Link to="/dashboard">
            <Button size="lg">Go to Dashboard</Button>
          </Link>
        ) : (
          <>
            <Link to="/register">
              <Button size="lg" data-testid="landing-register">
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
    </div>
  );
}
