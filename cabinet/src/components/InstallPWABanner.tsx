import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { usePWAInstall } from '@/hooks/usePWAInstall';

// =============================================
// Компонент баннера установки PWA
// =============================================
// Показывает предложение установить приложение, если:
//   - Приложение ещё не установлено
//   - Пользователь не отклонил предложение
//   - Мы не внутри Telegram WebApp
//
// На Android/Desktop: кнопка «Установить» (нативный промпт)
// На iOS: инструкция «Нажмите Поделиться → На экран Домой»

// Иконка смартфона
const PhoneIcon = () => (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3"
    />
  </svg>
);

// Иконка закрытия
const CloseIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
);

// Иконка галочки (для статуса «установлено»)
const CheckCircleIcon = () => (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  </svg>
);

// Иконка «Поделиться» (iOS Share)
const ShareIcon = () => (
  <svg className="inline-block h-4 w-4 align-text-bottom" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 8l5-5m0 0l5 5m-5-5v12" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
  </svg>
);

interface InstallPWABannerProps {
  /** Вариант отображения: card (bento-card) или compact (для Login) */
  variant?: 'card' | 'compact';
}

export function InstallPWABanner({ variant = 'card' }: InstallPWABannerProps) {
  const { t } = useTranslation();
  const { canInstall, isInstalled, isIOS, isDismissed, promptInstall, dismissInstall } =
    usePWAInstall();

  // Проверяем, находимся ли внутри Telegram WebApp
  const isTelegram =
    !!(window as unknown as { TelegramWebviewProxy?: unknown }).TelegramWebviewProxy ||
    window.location.hash.includes('tgWebApp') ||
    window.location.search.includes('tgWebApp');

  // Не показываем баннер, если:
  // - Внутри Telegram WebApp (там установка PWA не нужна)
  // - Приложение уже установлено и variant !== 'card' (в профиле покажем статус)
  if (isTelegram) return null;

  // --- Вариант «card» для Profile.tsx ---
  if (variant === 'card') {
    // Если установлено — показываем статус
    if (isInstalled) {
      return (
        <div className="flex items-center gap-3 rounded-xl border border-success-500/20 bg-success-500/5 p-4">
          <div className="text-success-400">
            <CheckCircleIcon />
          </div>
          <div>
            <p className="font-medium text-success-400">{t('pwa.installed')}</p>
            <p className="text-sm text-dark-400">{t('pwa.installedDesc')}</p>
          </div>
        </div>
      );
    }

    // iOS: инструкция по установке
    if (isIOS) {
      return (
        <div className="space-y-3">
          <div className="flex items-start gap-3 rounded-xl border border-accent-500/20 bg-accent-500/5 p-4">
            <div className="mt-0.5 text-accent-400">
              <PhoneIcon />
            </div>
            <div>
              <p className="font-medium text-dark-100">{t('pwa.installTitle')}</p>
              <p className="mt-1 text-sm text-dark-400">{t('pwa.installDesc')}</p>
              <div className="mt-3 space-y-2 text-sm text-dark-300">
                <p>
                  1. {t('pwa.ios.step1')} <ShareIcon />
                </p>
                <p>2. {t('pwa.ios.step2')}</p>
                <p>3. {t('pwa.ios.step3')}</p>
              </div>
            </div>
          </div>
        </div>
      );
    }

    // Android/Desktop: кнопка установки
    if (canInstall) {
      return (
        <div className="flex items-center justify-between rounded-xl border border-accent-500/20 bg-accent-500/5 p-4">
          <div className="flex items-center gap-3">
            <div className="text-accent-400">
              <PhoneIcon />
            </div>
            <div>
              <p className="font-medium text-dark-100">{t('pwa.installTitle')}</p>
              <p className="text-sm text-dark-400">{t('pwa.installDesc')}</p>
            </div>
          </div>
          <button
            onClick={promptInstall}
            className="shrink-0 rounded-xl bg-accent-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-400"
          >
            {t('pwa.installButton')}
          </button>
        </div>
      );
    }

    // Ничего не показываем, если нет возможности установить
    return null;
  }

  // --- Вариант «compact» для Login.tsx ---
  // Не показываем, если установлено или отклонено
  if (isInstalled || isDismissed) return null;
  // Не показываем, если нет возможности установить и не iOS
  if (!canInstall && !isIOS) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 10 }}
        transition={{ duration: 0.3, delay: 1 }}
        className="relative rounded-xl border border-dark-700/50 bg-dark-800/80 p-3"
      >
        {/* Кнопка закрытия */}
        <button
          onClick={dismissInstall}
          className="absolute right-2 top-2 rounded-lg p-1 text-dark-500 transition-colors hover:text-dark-300"
          aria-label="Close"
        >
          <CloseIcon />
        </button>

        <div className="flex items-center gap-3 pr-6">
          <div className="shrink-0 text-accent-400">
            <PhoneIcon />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-dark-200">{t('pwa.installTitle')}</p>
            {isIOS ? (
              <p className="mt-0.5 text-xs text-dark-400">
                {t('pwa.ios.compactHint')} <ShareIcon /> → {t('pwa.ios.step2Short')}
              </p>
            ) : (
              <button
                onClick={promptInstall}
                className="mt-1 text-xs font-medium text-accent-400 transition-colors hover:text-accent-300"
              >
                {t('pwa.installButton')} →
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
