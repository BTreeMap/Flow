import { Navigate } from "react-router";
import { useAuth } from "../auth";

interface Props {
  children: React.ReactNode;
  requiredRole?: string;
}

export function ProtectedRoute({ children, requiredRole }: Props) {
  const { isAuthenticated, isLoading, role } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && role !== requiredRole) {
    return (
      <div className="text-center py-16">
        <h2 className="text-2xl font-bold text-text mb-2">Access Denied</h2>
        <p className="text-text-muted">You do not have permission to view this page.</p>
      </div>
    );
  }

  return <>{children}</>;
}
