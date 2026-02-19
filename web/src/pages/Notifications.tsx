import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router";
import { Card, CardContent, CardHeader } from "../components/Card";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { getOrMintToken } from "../auth/token";
import { Bell, BellOff, Smartphone } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

function isIOS(): boolean {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function isStandalone(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches ||
    ("standalone" in navigator && (navigator as unknown as { standalone: boolean }).standalone);
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

  const showsIOSGuide = isIOS() && !isStandalone();

  // Check existing subscription on mount
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

  const subscribe = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      // Request notification permission
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== "granted") {
        setError("Notification permission was denied.");
        return;
      }

      // Get VAPID public key from backend
      const token = await getOrMintToken("http");
      const vapidRes = await fetch(`${API_BASE}/p/${projectId}/push/vapid-public-key`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!vapidRes.ok) throw new Error("Failed to fetch VAPID key");
      const { public_key } = await vapidRes.json();

      // Convert VAPID key to Uint8Array
      const padding = "=".repeat((4 - (public_key.length % 4)) % 4);
      const base64 = (public_key + padding).replace(/-/g, "+").replace(/_/g, "/");
      const rawData = atob(base64);
      const applicationServerKey = new Uint8Array(rawData.length);
      for (let i = 0; i < rawData.length; i++) {
        applicationServerKey[i] = rawData.charCodeAt(i);
      }

      // Subscribe via Push API
      const reg = await navigator.serviceWorker.ready;
      const subscription = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });

      // Send subscription to backend
      const subRes = await fetch(
        `${API_BASE}/p/${projectId}/push/subscribe`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            endpoint: subscription.endpoint,
            keys: subscription.toJSON().keys,
            user_agent: navigator.userAgent,
          }),
        },
      );
      if (!subRes.ok) throw new Error("Failed to register subscription");

      setSubscribed(true);
      setSuccess("Notifications enabled!");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enable notifications");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const unsubscribe = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await sub.unsubscribe();

        const token = await getOrMintToken("http");
        await fetch(`${API_BASE}/p/${projectId}/push/unsubscribe`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
      }
      setSubscribed(false);
      setSuccess("Notifications disabled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable notifications");
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
              <h2 className="text-lg font-semibold text-text">Add to Home Screen</h2>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-text-muted">
            <p>
              To receive push notifications on iOS, you need to install this app first:
            </p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Tap the <strong>Share</strong> button in Safari</li>
              <li>Select <strong>"Add to Home Screen"</strong></li>
              <li>Open the app from your Home Screen</li>
              <li>Come back here to enable notifications</li>
            </ol>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text">Push Notifications</h2>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <Alert variant="error">{error}</Alert>}
          {success && <Alert variant="success">{success}</Alert>}

          <div className="text-sm text-text-muted">
            {permission === "denied" ? (
              <p>
                Notifications are blocked. Please enable them in your browser settings.
              </p>
            ) : subscribed ? (
              <p>You are currently subscribed to push notifications for this project.</p>
            ) : (
              <p>
                Enable push notifications to receive reminders and updates even when
                the app is closed.
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
            Status: {permission === "granted" ? "✓ Permitted" : permission === "denied" ? "✗ Blocked" : "Not yet asked"}
            {subscribed ? " · Subscribed" : ""}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
