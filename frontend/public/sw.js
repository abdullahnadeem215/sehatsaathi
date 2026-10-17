// Sehat Saathi PWA Service Worker
// Provides offline caching, background alarm notifications, and emergency siren handling

const CACHE_NAME = 'sehat-saathi-v2'
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon.svg',
]

// Install: Cache static shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('SW cache.addAll non-critical warning:', err)
      })
    })
  )
  self.skipWaiting()
})

// Activate: Clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    })
  )
  self.clients.claim()
})

// Fetch: Network first with cache fallback for HTML/assets
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)

  // Bypass API and SSE streams
  if (url.pathname.startsWith('/api') || url.pathname.includes('/caregiver/events')) {
    return
  }

  // Handle static assets
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.status === 200) {
          const responseClone = response.clone()
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone)
          })
        }
        return response
      })
      .catch(async () => {
        const cached = await caches.match(event.request)
        if (cached) return cached
        if (event.request.headers.get('accept')?.includes('text/html')) {
          return caches.match('/index.html')
        }
        return new Response('Offline', { status: 503, statusText: 'Offline' })
      })
  )
})

// Background Emergency Alarm Notifications
// Rings like an alarm even if app is in background or phone is locked
self.addEventListener('message', (event) => {
  const data = event.data
  if (data && data.type === 'TRIGGER_ALARM') {
    const payload = data.payload || {}
    const title = payload.title || '🚨 EMERGENCY ALARM: Patient Heart Alert!'
    const body = payload.body || 'Immediate attention required! Heart discomfort or emergency reported.'

    const options = {
      body,
      icon: '/icon.svg',
      badge: '/icon.svg',
      tag: 'emergency-alarm',
      renotify: true,
      requireInteraction: true,
      silent: false,
      vibrate: [500, 250, 500, 250, 1000, 250, 1000],
      data: {
        alertId: payload.alertId,
        url: '/?role=caregiver&alertId=' + (payload.alertId || ''),
      },
      actions: [
        {
          action: 'open_alert',
          title: '🚨 Open Alert Now',
        },
        {
          action: 'silence',
          title: '🔕 Silence Alarm',
        },
      ],
    }

    self.registration.showNotification(title, options)
  }
})

// Handle Push notifications from web push server if configured
self.addEventListener('push', (event) => {
  let data = {
    title: '🚨 EMERGENCY ALARM: Patient Heart Alert!',
    body: 'Urgent: Patient reported chest pain or red-flag emergency.',
    alertId: null,
  }

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() }
    } catch (e) {
      data.body = event.data.text()
    }
  }

  const options = {
    body: data.body,
    icon: '/icon.svg',
    badge: '/icon.svg',
    tag: 'emergency-alarm',
    renotify: true,
    requireInteraction: true,
    vibrate: [500, 250, 500, 250, 1000, 250, 1000],
    data: {
      alertId: data.alertId,
      url: '/?role=caregiver',
    },
    actions: [
      { action: 'open_alert', title: '🚨 Open Alert Now' },
      { action: 'silence', title: '🔕 Silence Alarm' },
    ],
  }

  event.waitUntil(self.registration.showNotification(data.title, options))
})

// Notification Click Handler: Focus app or navigate to caregiver alert
self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  if (event.action === 'silence') {
    // Notify clients to stop siren
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      clients.forEach((client) => {
        client.postMessage({ type: 'SILENCE_SIREN' })
      })
    })
    return
  }

  // Open or focus the app
  const targetUrl = event.notification.data?.url || '/?role=caregiver'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          client.postMessage({
            type: 'NAVIGATE_TO_ALERT',
            alertId: event.notification.data?.alertId,
          })
          return client.focus()
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl)
      }
    })
  )
})
