// Service Worker for Flow Research PWA

const KEYVAL_DB_NAME = "keyval-store";
const KEYVAL_STORE_NAME = "keyval";
const DB_PRIVATE_KEY = "h4ckath0n_device_private_key";
const DB_DEVICE_ID = "h4ckath0n_device_id";
const DB_USER_ID = "h4ckath0n_user_id";
const AUD_HTTP = "h4ckath0n:http";
const TOKEN_LIFETIME_SECONDS = 900;

function base64UrlEncode(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function utf8Base64Url(value) {
  return base64UrlEncode(new TextEncoder().encode(value));
}

function openKeyvalDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(KEYVAL_DB_NAME);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}

async function keyvalGet(key) {
  const db = await openKeyvalDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(KEYVAL_STORE_NAME, "readonly");
      const store = tx.objectStore(KEYVAL_STORE_NAME);
      const req = store.get(key);
      req.onerror = () => reject(req.error);
      req.onsuccess = () => resolve(req.result ?? null);
    });
  } finally {
    db.close();
  }
}

async function mintHttpToken() {
  const [privateKey, deviceId, userId] = await Promise.all([
    keyvalGet(DB_PRIVATE_KEY),
    keyvalGet(DB_DEVICE_ID),
    keyvalGet(DB_USER_ID),
  ]);

  if (!privateKey) throw new Error("Missing device private key");
  if (!deviceId) throw new Error("Missing device id");
  if (!userId) throw new Error("Missing user id");

  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "ES256", typ: "JWT", kid: String(deviceId) };
  const payload = {
    sub: String(userId),
    iat: now,
    exp: now + TOKEN_LIFETIME_SECONDS,
    aud: AUD_HTTP,
  };

  const signingInput = `${utf8Base64Url(JSON.stringify(header))}.${utf8Base64Url(JSON.stringify(payload))}`;
  const signatureRaw = await crypto.subtle.sign(
    { name: "ECDSA", hash: { name: "SHA-256" } },
    privateKey,
    new TextEncoder().encode(signingInput),
  );
  const signature = base64UrlEncode(new Uint8Array(signatureRaw));
  return `${signingInput}.${signature}`;
}

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = { title: "Flow Research", body: "You have a new message." };
  try {
    if (event.data) {
      payload = event.data.json();
    }
  } catch {
    // fallback to default payload
  }

  // Handle dismiss action (sync across devices)
  if (payload.data?.action === "dismiss" && payload.data?.notification_id) {
    event.waitUntil(
      self.registration.getNotifications().then((notifications) => {
        for (const notification of notifications) {
          // Check if this is the notification to dismiss
          if (notification.data && notification.data.notification_id === payload.data.notification_id) {
            notification.close();
          }
        }
      })
    );
    return;
  }

  // Build notification data, merging top-level url and nested data fields
  const notificationData = {
    ...(payload.data || {}),
    url: payload.url || payload.data?.url || null,
    project_id: payload.data?.project_id || null,
    notification_id: payload.data?.notification_id || null,
  };

  // Try to extract project_id from url if not explicitly provided
  if (!notificationData.project_id && notificationData.url) {
    const urlMatch = notificationData.url.match(/\/p\/([^/]+)/);
    if (urlMatch) {
      notificationData.project_id = urlMatch[1];
    }
  }

  // Show notification
  event.waitUntil(
    self.registration.showNotification(payload.title || "Flow Research", {
      body: payload.body || "",
      icon: payload.icon || "/icons/icon-192.png",
      data: notificationData,
      actions: payload.actions || [],
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const data = event.notification.data || {};
  const projectId = data.project_id;
  const notificationId = data.notification_id;

  if (event.action) {
    if (!projectId) {
      console.warn(
        "Feedback action ignored: missing project_id in notification data",
        { notificationId, action: event.action },
      );
      return;
    }
    event.waitUntil(
      (async () => {
        const token = await mintHttpToken();
        await fetch(`/api/p/${projectId}/chat/events/feedback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            action_id: event.action,
            notification_id: notificationId,
            project_id: projectId,
          }),
        });
      })().catch((err) => console.error("Feedback sync failed:", err)),
    );
    return;
  }

  // Build deep-link URL
  let urlPath;
  if (data.url) {
    urlPath = data.url;
  } else if (projectId && notificationId) {
    urlPath = `/p/${projectId}/chat?nid=${notificationId}`;
  } else if (projectId) {
    urlPath = `/p/${projectId}/chat`;
  } else {
    urlPath = "/dashboard";
  }

  // Resolve to absolute URL for proper comparison
  const target = new URL(urlPath, self.location.origin).href;

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        // Try to focus existing window with matching URL
        for (const client of clients) {
          if (client.url === target && "focus" in client) {
            return client.focus();
          }
        }
        // Try to navigate an existing window to the target
        for (const client of clients) {
          if ("navigate" in client && "focus" in client) {
            return client.navigate(target).then((c) => c && c.focus());
          }
        }
        // If not found, open new
        if (self.clients.openWindow) {
          return self.clients.openWindow(target);
        }
      }),
  );
});
