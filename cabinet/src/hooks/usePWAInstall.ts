import { useState, useEffect, useCallback, useRef } from 'react';

// =============================================
// Хук для управления установкой PWA-приложения
// =============================================
// Предоставляет:
//   - canInstall: можно ли показать нативный промпт установки (Android/Desktop Chrome)
//   - isInstalled: запущено ли приложение в standalone-режиме (уже установлено)
//   - isIOS: устройство iOS (для показа ручной инструкции)
//   - isDismissed: пользователь уже отклонил предложение
//   - promptInstall(): вызвать нативный диалог установки
//   - dismissInstall(): скрыть баннер и запомнить решение

// Ключ в localStorage для запоминания отказа от установки
const DISMISS_KEY = 'pwa-install-dismissed';
// Время (мс), после которого снова показать предложение (7 дней)
const DISMISS_DURATION = 7 * 24 * 60 * 60 * 1000;

// Тип события beforeinstallprompt (нестандартный, не во всех браузерах)
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export function usePWAInstall() {
  // Сохраняем ссылку на событие beforeinstallprompt
  const deferredPromptRef = useRef<BeforeInstallPromptEvent | null>(null);

  // Можно ли установить (доступен ли нативный промпт)
  const [canInstall, setCanInstall] = useState(false);

  // Приложение уже установлено (standalone-режим)
  const [isInstalled, setIsInstalled] = useState(false);

  // Пользователь уже отклонил предложение
  const [isDismissed, setIsDismissed] = useState(false);

  // Определение iOS-устройства
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    // Проверяем, запущено ли приложение в standalone-режиме
    const isStandalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (window.navigator as unknown as { standalone?: boolean }).standalone === true;

    setIsInstalled(isStandalone);

    // Определяем iOS-устройство
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isiOSDevice = /iphone|ipad|ipod/.test(userAgent);
    setIsIOS(isiOSDevice);

    // Проверяем, отклонял ли пользователь установку ранее
    const dismissedAt = localStorage.getItem(DISMISS_KEY);
    if (dismissedAt) {
      const elapsed = Date.now() - parseInt(dismissedAt, 10);
      if (elapsed < DISMISS_DURATION) {
        // Ещё не прошло 7 дней — не показываем
        setIsDismissed(true);
      } else {
        // Прошло 7 дней — снова показываем
        localStorage.removeItem(DISMISS_KEY);
      }
    }

    // Перехватываем событие beforeinstallprompt (Chrome/Edge/Samsung Internet)
    const handleBeforeInstallPrompt = (e: Event) => {
      // Предотвращаем стандартный мини-промпт браузера
      e.preventDefault();
      // Сохраняем событие для последующего вызова
      deferredPromptRef.current = e as BeforeInstallPromptEvent;
      setCanInstall(true);
    };

    // Обработчик события appinstalled (приложение установлено)
    const handleAppInstalled = () => {
      setIsInstalled(true);
      setCanInstall(false);
      deferredPromptRef.current = null;
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  // Вызвать нативный диалог установки
  const promptInstall = useCallback(async () => {
    const prompt = deferredPromptRef.current;
    if (!prompt) return false;

    try {
      // Показываем нативный промпт установки
      await prompt.prompt();
      // Ожидаем решение пользователя
      const { outcome } = await prompt.userChoice;

      if (outcome === 'accepted') {
        // Пользователь принял установку
        setIsInstalled(true);
        setCanInstall(false);
      }

      // После вызова prompt событие можно использовать только один раз
      deferredPromptRef.current = null;
      return outcome === 'accepted';
    } catch {
      return false;
    }
  }, []);

  // Отклонить предложение установки (запоминаем на 7 дней)
  const dismissInstall = useCallback(() => {
    setIsDismissed(true);
    localStorage.setItem(DISMISS_KEY, Date.now().toString());
  }, []);

  return {
    /** Можно ли показать нативный промпт установки */
    canInstall,
    /** Приложение уже установлено (standalone-режим) */
    isInstalled,
    /** iOS-устройство (нужна ручная инструкция) */
    isIOS,
    /** Пользователь отклонил предложение */
    isDismissed,
    /** Вызвать нативный диалог установки */
    promptInstall,
    /** Скрыть баннер и запомнить */
    dismissInstall,
  };
}
