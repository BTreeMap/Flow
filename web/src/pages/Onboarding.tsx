import { Navigate, useParams } from "react-router";

export function Onboarding() {
  const { projectId } = useParams<{ projectId: string }>();
  return <Navigate to={`/p/${projectId}/onboarding/notifications`} replace />;
}
