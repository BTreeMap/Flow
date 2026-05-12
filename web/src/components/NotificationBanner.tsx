import { useParams } from "react-router";
import { AlertTriangle, Bell } from "lucide-react";
import { usePushNotifications } from "../hooks/usePushNotifications";
import { Button } from "./Button";

export function NotificationBanner() {
  const { projectId } = useParams<{ projectId: string }>();
  const {
    permission,
    subscribed,
    loading,
    initializing,
    subscribe,
    pushNotConfigured,
  } = usePushNotifications();

  // If we are not in a project route, don't show the banner
  if (!projectId) return null;

  // If initializing, already subscribed, or VAPID not configured, don't show
  if (initializing || subscribed || pushNotConfigured) return null;

  // If permission is denied, show instructions
  if (permission === "denied") {
    return (
      <div className="bg-error/10 border-b border-error/20 p-3 flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-danger shrink-0" />
        <p className="text-sm text-danger flex-1">
          Notifications are blocked. Please enable them in your browser settings
          to receive daily nudges.
        </p>
      </div>
    );
  }

  // If permission is default (or granted but not subscribed for some reason), show enable button
  return (
    <div className="bg-primary/10 border-b border-primary/20 p-3 flex items-center gap-3">
      <Bell className="w-5 h-5 text-primary shrink-0" />
      <p className="text-sm text-primary-dark flex-1">
        Don't miss a nudge! Enable notifications to stay on track.
      </p>
      <Button size="sm" onClick={() => void subscribe()} disabled={loading}>
        {loading ? "Enabling..." : "Enable"}
      </Button>
    </div>
  );
}
