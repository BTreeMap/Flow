import { Link } from "react-router";
import { Shield } from "lucide-react";
import { useAuth } from "../auth";
import { Button } from "../components/Button";

export function Landing() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="max-w-2xl mx-auto text-center py-16">
      <div className="flex justify-center mb-6">
        <div className="p-4 bg-primary/10 rounded-3xl">
          <Shield className="w-12 h-12 text-primary" />
        </div>
      </div>

      <h1 className="text-4xl sm:text-5xl font-bold text-text mb-4">
        Welcome to <span className="text-primary">{"Flow"}</span>
      </h1>

      <p className="text-lg text-text-muted mb-8 max-w-xl mx-auto">
        Flow is an HCI research platform for project-based coaching chats with
        passkey login, real-time conversation updates, and optional
        notifications.
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
                Register
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
