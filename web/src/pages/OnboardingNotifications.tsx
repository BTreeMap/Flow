import { useNavigate, useParams } from "react-router";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { Bell, Smartphone } from "lucide-react";
import {
  usePushNotifications,
  isIOS,
  isStandalone,
} from "../hooks/usePushNotifications";

export function OnboardingNotifications() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const {
    permission,
    subscribed,
    loading,
    error,
    success,
    subscribe,
    pushNotConfigured,
  } = usePushNotifications(projectId);

  const showsIOSGuide = isIOS() && !isStandalone();

  const handleContinue = () => {
    navigate(`/p/${projectId}/chat`);
  };

  return (
    <div className="max-w-xl mx-auto">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="w-6 h-6 text-primary" />
            <h1 className="text-xl font-bold text-text">Don't miss a nudge</h1>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-text-muted">
            To get the most out of this experiment, please enable push
            notifications. This ensures you receive nudges at the times you set
            in chat.
          </p>

          {showsIOSGuide && (
            <div className="bg-surface-muted p-4 rounded-md space-y-2 text-sm text-text-muted">
              <div className="flex items-center gap-2 font-semibold text-text">
                <Smartphone className="w-4 h-4" />
                Add to Home Screen
              </div>
              <p>
                To receive push notifications on iOS, you need to install this
                app first:
              </p>
              <ol className="list-decimal list-inside space-y-1 ml-2">
                <li>
                  Tap the <strong>Share</strong> button in Safari
                </li>
                <li>
                  Select <strong>"Add to Home Screen"</strong>
                </li>
                <li>Open the app from your Home Screen</li>
              </ol>
            </div>
          )}

          {error && <Alert variant="error">{error}</Alert>}
          {success && <Alert variant="success">{success}</Alert>}
          {pushNotConfigured && (
            <Alert variant="warning">
              Push notifications are not configured on the server.
            </Alert>
          )}

          <div className="flex flex-col gap-3 pt-2">
            {subscribed ? (
              <Button onClick={handleContinue} className="w-full">
                Continue to Chat
              </Button>
            ) : (
              <>
                <Button
                  onClick={() => void subscribe()}
                  disabled={
                    loading ||
                    permission === "denied" ||
                    showsIOSGuide ||
                    pushNotConfigured
                  }
                  className="w-full"
                >
                  {loading ? "Enabling..." : "Enable Notifications"}
                </Button>

                {!loading && (
                  <Button
                    variant="secondary"
                    onClick={handleContinue}
                    className="w-full"
                  >
                    Skip for now
                  </Button>
                )}
              </>
            )}
          </div>

          {permission === "denied" && (
            <p className="text-sm text-error mt-2">
              Notifications are blocked. Please enable them in your browser
              settings to continue.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
