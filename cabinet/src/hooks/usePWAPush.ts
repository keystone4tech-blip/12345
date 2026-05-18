import { useState, useEffect, useCallback } from 'react';
import { pushApi } from '../api';

/**
 * Вспомогательная функция для преобразования публичного VAPID ключа
 * из URL-safe Base64 в Uint8Array для браузерного PushManager.
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Пользовательский React-хук для работы с Web Push в PWA.
 * Предоставляет текущий статус подписки и методы подписки/отписки.
 */
export function usePWAPush() {
  const [isSupported, setIsSupported] = useState(false);
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Получает текущую подписку на пуши в браузере
  const getSubscription = useCallback(async (): Promise<PushSubscription | null> => {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      return null;
    }
    const registration = await navigator.serviceWorker.ready;
    return await registration.pushManager.getSubscription();
  }, []);

  // Проверяет поддержку пушей и наличие активной подписки
  const checkSubscription = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        setIsSupported(false);
        setLoading(false);
        return;
      }

      setIsSupported(true);
      setPermission(Notification.permission);

      const subscription = await getSubscription();
      setIsSubscribed(!!subscription);
    } catch (err: any) {
      console.error('[Web Push] Error checking subscription:', err);
      setError(err?.message || 'Ошибка проверки подписки на уведомления');
    } finally {
      setLoading(false);
    }
  }, [getSubscription]);

  // Запуск при монтировании хука
  useEffect(() => {
    checkSubscription();
  }, [checkSubscription]);

  // Подписка на Web Push
  const subscribe = async (): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      if (!isSupported) {
        throw new Error('Push-уведомления не поддерживаются в этом браузере.');
      }

      // 1. Запрашиваем права на показ уведомлений
      const result = await Notification.requestPermission();
      setPermission(result);

      if (result !== 'granted') {
        throw new Error('Разрешение на отправку уведомлений отклонено.');
      }

      // 2. Загружаем VAPID ключ с сервера
      const { public_key: vapidKey } = await pushApi.getVapidKey();
      if (!vapidKey) {
        throw new Error('Публичный VAPID-ключ не настроен на сервере.');
      }

      // 3. Подписываемся через PushManager
      const registration = await navigator.serviceWorker.ready;
      const convertedVapidKey = urlBase64ToUint8Array(vapidKey);

      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: convertedVapidKey as any,
      });

      // 4. Отправляем данные подписки на бэкенд
      const rawSub = subscription.toJSON();
      if (!rawSub.endpoint || !rawSub.keys?.p256dh || !rawSub.keys?.auth) {
        throw new Error('Браузер вернул неполные ключи подписки.');
      }

      await pushApi.subscribe({
        endpoint: rawSub.endpoint,
        keys: {
          p256dh: rawSub.keys.p256dh,
          auth: rawSub.keys.auth,
        },
      });

      setIsSubscribed(true);
      return true;
    } catch (err: any) {
      console.error('[Web Push] Subscription failed:', err);
      setError(err?.message || 'Не удалось настроить push-уведомления');
      return false;
    } finally {
      setLoading(false);
    }
  };

  // Отмена подписки на Web Push
  const unsubscribe = async (): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      const subscription = await getSubscription();
      if (subscription) {
        // Удаляем с бэкенда
        await pushApi.unsubscribe(subscription.endpoint);
        
        // Удаляем локально в браузере
        await subscription.unsubscribe();
      }
      setIsSubscribed(false);
      return true;
    } catch (err: any) {
      console.error('[Web Push] Unsubscription failed:', err);
      setError(err?.message || 'Не удалось отключить push-уведомления');
      return false;
    } finally {
      setLoading(false);
    }
  };

  return {
    isSupported,
    isSubscribed,
    permission,
    loading,
    error,
    subscribe,
    unsubscribe,
    checkSubscription,
  };
}
