// Service Worker для фоновой обработки Web Push-уведомлений (PWA Фаза 2)

self.addEventListener('push', function(event) {
  if (!event.data) {
    console.log('[Service Worker] Push event received but had no data.');
    return;
  }

  let data = {};
  try {
    data = event.data.json();
  } catch (e) {
    console.warn('[Service Worker] Error parsing push data as JSON, falling back to text:', e);
    data = {
      title: 'Уведомление от MozhnoVPN',
      body: event.data.text()
    };
  }

  const title = data.title || 'MozhnoVPN';
  const options = {
    body: data.body || '',
    icon: data.icon || '/icons/icon-192x192.png',
    badge: data.badge || '/icons/icon-192x192.png',
    vibrate: data.vibrate || [100, 50, 100],
    data: data.data || { url: '/' }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  // Определяем целевой URL для перехода при клике
  let urlToOpen = '/';
  if (event.notification.data && event.notification.data.url) {
    urlToOpen = event.notification.data.url;
  }

  event.waitUntil(
    clients.matchAll({
      type: 'window',
      includeUncontrolled: true
    }).then(function(windowClients) {
      // Ищем уже открытую вкладку нашего кабинета
      for (let i = 0; i < windowClients.length; i++) {
        let client = windowClients[i];
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          if (client.navigate) {
            client.navigate(urlToOpen);
          }
          return client.focus();
        }
      }
      // Если вкладка закрыта, открываем новую
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
