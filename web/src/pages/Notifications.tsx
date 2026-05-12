import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { Bell, BellOff, Smartphone, AlertTriangle } from "lucide-react";
import {
  usePushNotifications,
  isIOS,
  isStandalone,
} from "../hooks/usePushNotifications";

export function Notifications() {
  const {
    permission,
    subscribed,
    loading,
    error,
    success,
    pushNotConfigured,
    subscribe,
    unsubscribe,
  } = usePushNotifications();

  const showsIOSGuide = isIOS() && !isStandalone();

  return (
    <div className="max-w-md mx-auto space-y-4">
      <h1 className="text-2xl font-bold text-text">Notifications</h1>

      {showsIOSGuide && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Smartphone className="w-5 h-5 text-primary" />
              <h2 className="text-lg font-semibold text-text">
                Add to Home Screen
              </h2>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-text-muted">
            <p>
              To receive push notifications on iOS, you need to install this app
              first:
            </p>
            <ol className="list-decimal list-inside space-y-1">
              <li>
                Tap the <strong>Share</strong> button in Safari
              </li>
              <li>
                Select <strong>"Add to Home Screen"</strong>
              </li>
              <li>Open the app from your Home Screen</li>
              <li>Come back here to enable notifications</li>
            </ol>
          </CardContent>
        </Card>
      )}

      {pushNotConfigured && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-warning" />
              <h2 className="text-lg font-semibold text-text">
                Push not configured
              </h2>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-text-muted">
              VAPID keys are missing on the server, so push notifications are
              disabled. See{" "}
              <a
                href="https://github.com/BTreeMap/Flow#vapid-web-push-configuration"
                target="_blank"
                rel="noreferrer"
                className="text-primary underline"
              >
                README VAPID configuration
              </a>
              .
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text">
              Push Notifications
            </h2>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <Alert variant="error">{error}</Alert>}
          {success && <Alert variant="success">{success}</Alert>}

          <div className="text-sm text-text-muted">
            {permission === "denied" ? (
              <p>
                Notifications are blocked. Please enable them in your browser
                settings.
              </p>
            ) : subscribed ? (
              <p>
                You are currently subscribed to push notifications for this
                project.
              </p>
            ) : (
              <p>
                Enable push notifications to receive reminders and updates even
                when the app is closed.
              </p>
            )}
          </div>

          {!("PushManager" in window) ? (
            <Alert variant="warning">
              Push notifications are not supported in this browser.
            </Alert>
          ) : subscribed ? (
            <Button
              variant="secondary"
              onClick={() => void unsubscribe()}
              disabled={loading}
              className="w-full"
            >
              <BellOff className="w-4 h-4" />
              {loading ? "Disabling…" : "Disable Notifications"}
            </Button>
          ) : (
            <Button
              onClick={() => void subscribe()}
              disabled={loading || permission === "denied" || showsIOSGuide}
              className="w-full"
            >
              <Bell className="w-4 h-4" />
              {loading ? "Enabling…" : "Enable Notifications"}
            </Button>
          )}

          <p className="text-xs text-text-muted">
            Status:{" "}
            {permission === "granted"
              ? "✓ Permitted"
              : permission === "denied"
                ? "✗ Blocked"
                : "Not yet asked"}
            {subscribed ? " · Subscribed" : ""}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
