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

  event.waitUntil(
    self.registration.showNotification(payload.title || "Flow Research", {
      body: payload.body || "",
      icon: "/vite.svg",
      data: payload.data || {},
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const projectId = event.notification.data?.project_id;
  const url = projectId ? `/p/${projectId}/chat` : "/dashboard";

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          if (client.url.includes(url) && "focus" in client) {
            return client.focus();
          }
        }
        if (self.clients.openWindow) {
          return self.clients.openWindow(url);
        }
      })
  );
});
