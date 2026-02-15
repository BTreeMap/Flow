import { useAuth } from "../auth";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Shield, Users } from "lucide-react";
import { Alert } from "../components/Alert";

export function Admin() {
  const { userId, role } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">Admin Panel</h1>
        <p className="text-text-muted">Server-side RBAC enforces all admin operations</p>
      </div>

      <Alert variant="info">
        This page is role-gated in the frontend. However, all admin operations are enforced
        server-side. The server derives roles from the database, never from JWT claims.
      </Alert>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text">Admin Info</h2>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <Users className="w-4 h-4 text-text-muted" />
            <span className="text-text-muted">User ID:</span>
            <span className="font-mono text-text">{userId}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Shield className="w-4 h-4 text-text-muted" />
            <span className="text-text-muted">Role:</span>
            <span className="font-medium text-text capitalize">{role}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
