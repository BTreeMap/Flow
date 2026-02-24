import { useState, useEffect, useCallback } from "react";
import api from "../api/client";

export function isIOS(): boolean {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function isStandalone(): boolean {
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

export function usePushNotifications(projectId?: string) {
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "default",
  );
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pushNotConfigured, setPushNotConfigured] = useState(false);

  // Check initial subscription status
  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        setInitializing(false);
        return;
      }
      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        setSubscribed(!!sub);
      } catch {
        // ignore
      } finally {
        setInitializing(false);
      }
    })();
  }, []);

  // Check if VAPID is configured on the backend
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

  return {
    permission,
    subscribed,
    loading,
    initializing,
    error,
    success,
    pushNotConfigured,
    subscribe,
    unsubscribe,
    setError, // Allowing components to clear error if needed
    setSuccess, // Allowing components to clear success if needed
  };
}
