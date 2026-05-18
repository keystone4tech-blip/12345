import apiClient from './client';

export interface PushSubscriptionKeys {
  p256dh: string;
  auth: string;
}

export interface PushSubscriptionData {
  endpoint: string;
  keys: PushSubscriptionKeys;
}

export const pushApi = {
  // Получить публичный VAPID-ключ сервера
  getVapidKey: async (): Promise<{ public_key: string }> => {
    const response = await apiClient.get<{ public_key: string }>('/cabinet/push/vapid-key');
    return response.data;
  },

  // Сохранить подписку на пуш-уведомления на бэкенде
  subscribe: async (data: PushSubscriptionData): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post<{ success: boolean; message: string }>(
      '/cabinet/push/subscribe',
      data
    );
    return response.data;
  },

  // Удалить подписку на пуш-уведомления
  unsubscribe: async (endpoint: string): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post<{ success: boolean; message: string }>(
      '/cabinet/push/unsubscribe',
      { endpoint }
    );
    return response.data;
  },
};
