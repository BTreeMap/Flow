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

const SUB_ID_STORAGE_KEY = "flow_push_subscription_id";

/** Shape of a single subscription returned by the debug list endpoint. */
interface WebPushSubscriptionInfo {
  id: number;
  endpoint: string;
  user_agent: string;
  created_at: string | null;
}

/** Extract the subscriptions array from the untyped backend response. */
function extractSubscriptions(data: unknown): WebPushSubscriptionInfo[] {
  if (
    data &&
    typeof data === "object" &&
    "subscriptions" in data &&
    Array.isArray((data as { subscriptions: unknown }).subscriptions)
  ) {
    return (data as { subscriptions: WebPushSubscriptionInfo[] }).subscriptions;
  }
  return [];
}

/**
 * User-scoped push notification management.
 * No projectId required — subscriptions are global per user.
 */
export function usePushNotifications() {
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "default",
  );
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pushNotConfigured, setPushNotConfigured] = useState(false);
  const [hasStaleBrowserSubscription, setHasStaleBrowserSubscription] =
    useState(false);

  // Check initial subscription status via backend
  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        setInitializing(false);
        return;
      }
      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (!sub) {
          setSubscribed(false);
          setInitializing(false);
          return;
        }
        // Check backend for user-scoped subscription
        const { data } = await api.GET(
          "/notifications/webpush/subscriptions",
        );
        const subs = extractSubscriptions(data);
        const registered = subs.some(
          (s) => s.endpoint === sub.endpoint,
        );
        if (!registered) {
          // Browser has a subscription the backend doesn't know about — stale
          setHasStaleBrowserSubscription(true);
          localStorage.removeItem(SUB_ID_STORAGE_KEY);
        }
        setSubscribed(registered);
      } catch {
        // ignore
      } finally {
        setInitializing(false);
      }
    })();
  }, []);

  // Check if VAPID is configured on the backend
  useEffect(() => {
    (async () => {
      const { error: apiError } = await api.GET(
        "/notifications/webpush/vapid-public-key",
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
  }, []);

  const subscribe = useCallback(async () => {
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
        "/notifications/webpush/vapid-public-key",
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

      // If browser has a stale subscription, unsubscribe first to get a fresh endpoint
      if (hasStaleBrowserSubscription) {
        const existingSub = await reg.pushManager.getSubscription();
        if (existingSub) {
          await existingSub.unsubscribe();
        }
        setHasStaleBrowserSubscription(false);
      }

      // Reuse existing browser subscription if available, otherwise create new
      let subscription = await reg.pushManager.getSubscription();
      if (!subscription) {
        subscription = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey,
        });
      }

      const { data: subData, error: subscribeError } = await api.POST(
        "/notifications/webpush/subscriptions",
        {
          body: {
            endpoint: subscription.endpoint,
            keys: getSubscriptionKeys(subscription),
            user_agent: navigator.userAgent,
          },
        },
      );
      if (subscribeError) throw new Error("Failed to register subscription");

      // Store subscription_id for later unsubscribe
      if (subData?.subscription_id) {
        localStorage.setItem(SUB_ID_STORAGE_KEY, String(subData.subscription_id));
      }

      setSubscribed(true);
      setSuccess("Notifications enabled!");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to enable notifications",
      );
    } finally {
      setLoading(false);
    }
  }, [hasStaleBrowserSubscription]);

  const unsubscribe = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      // Find subscription_id from localStorage or backend
      let subId = localStorage.getItem(SUB_ID_STORAGE_KEY);

      if (!subId) {
        // Look up from backend by endpoint
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
          const { data } = await api.GET(
            "/notifications/webpush/subscriptions",
          );
          const subs = extractSubscriptions(data);
          const match = subs.find(
            (s) => s.endpoint === sub.endpoint,
          );
          if (match) subId = String(match.id);
        }
      }

      if (subId) {
        const { error: delError } = await api.DELETE(
          "/notifications/webpush/subscriptions/{subscription_id}",
          { params: { path: { subscription_id: Number(subId) } } },
        );
        // Clear stale localStorage even on 404 (e.g., after migration)
        localStorage.removeItem(SUB_ID_STORAGE_KEY);
        if (delError) {
          // If the stored ID was stale, fall back to endpoint lookup
          const reg2 = await navigator.serviceWorker.ready;
          const sub2 = await reg2.pushManager.getSubscription();
          if (sub2) {
            const { data: fallbackData } = await api.GET(
              "/notifications/webpush/subscriptions",
            );
            const fallbackSubs = extractSubscriptions(fallbackData);
            const match = fallbackSubs.find(
              (s) => s.endpoint === sub2.endpoint,
            );
            if (match) {
              await api.DELETE(
                "/notifications/webpush/subscriptions/{subscription_id}",
                { params: { path: { subscription_id: match.id } } },
              );
            }
          }
        }
      }

      // Also unsubscribe in the browser (global, since subscriptions are user-scoped)
      const reg = await navigator.serviceWorker.ready;
      const browserSub = await reg.pushManager.getSubscription();
      if (browserSub) {
        await browserSub.unsubscribe();
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
  }, []);

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
    setError,
    setSuccess,
  };
}
