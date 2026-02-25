// Service Worker for Flow Research PWA

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

  // Show notification
  event.waitUntil(
    self.registration.showNotification(payload.title || "Flow Research", {
      body: payload.body || "",
      icon: payload.icon || "/vite.svg",
      data: payload.data || {},
      actions: payload.actions || [],
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const projectId = event.notification.data?.project_id;
  const url = event.notification.data?.url || (projectId ? `/p/${projectId}/updates` : "/dashboard");

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        // Try to focus existing window
        for (const client of clients) {
          if (client.url === url && "focus" in client) {
            return client.focus();
          }
        }
        // If not found, open new
        if (self.clients.openWindow) {
          return self.clients.openWindow(url);
        }
      }),
  );
});
