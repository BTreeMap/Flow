import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { Bell, BellOff, Smartphone, AlertTriangle } from "lucide-react";
import api from "../api/client";

function isIOS(): boolean {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in navigator &&
      (navigator as unknown as { standalone: boolean }).standalone)
  );
}

function extractErrorDetail(error: unknown, fallback: string): string {
  if (
    error &&
    typeof error === "object" &&
    "detail" in error &&
    typeof (error as { detail?: unknown }).detail === "string"
  ) {
    return (error as { detail: string }).detail;
  }
  return fallback;
}

function getSubscriptionKeys(
  subscription: PushSubscription,
): { auth: string; p256dh: string } {
  const keys = subscription.toJSON().keys;
  if (!keys?.auth || !keys?.p256dh) {
    throw new Error("Push subscription keys were missing from the browser.");
  }
  return { auth: keys.auth, p256dh: keys.p256dh };
}

export function Notifications() {
  const { projectId } = useParams<{ projectId: string }>();
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "default",
  );
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pushNotConfigured, setPushNotConfigured] = useState(false);

  const showsIOSGuide = isIOS() && !isStandalone();

  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        setSubscribed(!!sub);
      } catch {
        // ignore
      }
    })();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    (async () => {
      const { error: apiError } = await api.GET(
        "/p/{project_id}/push/vapid-public-key",
        {
          params: { path: { project_id: projectId } },
        },
      );
      if (!apiError) return;
      const detail = extractErrorDetail(apiError, "");
      if (
        detail.toLowerCase().includes("vapid") &&
        detail.includes("not configured")
      ) {
        setPushNotConfigured(true);
      }
    })();
  }, [projectId]);

  const subscribe = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== "granted") {
        setError("Notification permission was denied.");
        return;
      }

      const { data: vapidData, error: vapidError } = await api.GET(
        "/p/{project_id}/push/vapid-public-key",
        {
          params: { path: { project_id: projectId } },
        },
      );
      if (vapidError) {
        const detail = extractErrorDetail(
          vapidError,
          "Failed to fetch VAPID key",
        );
        if (
          detail.toLowerCase().includes("vapid") &&
          detail.includes("not configured")
        ) {
          setPushNotConfigured(true);
        }
        throw new Error(detail);
      }
      const { public_key } = vapidData;

      const padding = "=".repeat((4 - (public_key.length % 4)) % 4);
      const base64 = (public_key + padding)
        .replace(/-/g, "+")
        .replace(/_/g, "/");
      const rawData = atob(base64);
      const applicationServerKey = new Uint8Array(rawData.length);
      for (let i = 0; i < rawData.length; i++) {
        applicationServerKey[i] = rawData.charCodeAt(i);
      }

      const reg = await navigator.serviceWorker.ready;
      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });

      const { error: subscribeError } = await api.POST(
        "/p/{project_id}/push/subscribe",
        {
          params: { path: { project_id: projectId } },
          body: {
            endpoint: subscription.endpoint,
            keys: getSubscriptionKeys(subscription),
            user_agent: navigator.userAgent,
          },
        },
      );
      if (subscribeError) throw new Error("Failed to register subscription");

      setSubscribed(true);
      setSuccess("Notifications enabled!");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to enable notifications",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const unsubscribe = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await sub.unsubscribe();
        await api.POST("/p/{project_id}/push/unsubscribe", {
          params: { path: { project_id: projectId } },
          body: { endpoint: sub.endpoint },
        });
      }
      setSubscribed(false);
      setSuccess("Notifications disabled.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to disable notifications",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId]);

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
