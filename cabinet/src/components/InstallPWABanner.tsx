import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import { usePWAInstall } from '@/hooks/usePWAInstall';
import { Card } from '@/components/data-display/Card';

// Иконки
const PhoneIcon = () => (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3" />
  </svg>
);

const CloseIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const CheckCircleIcon = () => (
  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ShareIcon = () => (
  <svg className="inline-block h-4 w-4 align-text-bottom" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 8l5-5m0 0l5 5m-5-5v12" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 15v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
  </svg>
);

const BrowserIcon = () => (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
  </svg>
);

interface InstallPWABannerProps {
  /** Вариант отображения: card (для профиля), compact (для Login), global (для шапки) */
  variant?: 'card' | 'compact' | 'global';
}

export function InstallPWABanner({ variant = 'card' }: InstallPWABannerProps) {
  const { t } = useTranslation();
  const { canInstall, isInstalled, isIOS, isDismissed, promptInstall, dismissInstall } = usePWAInstall();
  const [copied, setCopied] = useState(false);

  // Проверяем Telegram WebApp
  const isTelegram =
    !!(window as unknown as { TelegramWebviewProxy?: unknown }).TelegramWebviewProxy ||
    window.location.hash.includes('tgWebApp') ||
    window.location.search.includes('tgWebApp');

  const copyUrl = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Если приложение уже установлено
  if (isInstalled) {
    if (variant === 'card') {
      return (
        <Card>
          <h2 className="mb-4 text-lg font-semibold text-dark-100">{t('pwa.sectionTitle')}</h2>
          <div className="flex items-center gap-3 rounded-xl border border-success-500/20 bg-success-500/5 p-4">
            <div className="text-success-400"><CheckCircleIcon /></div>
            <div>
              <p className="font-medium text-success-400">{t('pwa.installed')}</p>
              <p className="text-sm text-dark-400">{t('pwa.installedDesc')}</p>
            </div>
          </div>
        </Card>
      );
    }
    return null; // Глобальный и компактный баннеры скрываем
  }

  // Если отклонили (кроме карточки профиля)
  if (isDismissed && variant !== 'card') {
    return null;
  }

  // === ЛОГИКА ОТОБРАЖЕНИЯ ===
  
  // 1. Для Telegram WebApp
  if (isTelegram) {
    if (variant === 'card') {
      return (
        <Card>
          <h2 className="mb-4 text-lg font-semibold text-dark-100">{t('pwa.sectionTitle')}</h2>
          <div className="flex flex-col gap-3 rounded-xl border border-accent-500/20 bg-accent-500/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="text-accent-400"><BrowserIcon /></div>
              <div>
                <p className="font-medium text-dark-100">Установка в Telegram недоступна</p>
                <p className="text-sm text-dark-400">Откройте кабинет в системном браузере (Chrome/Safari), чтобы установить приложение</p>
              </div>
            </div>
            <button
              onClick={copyUrl}
              className="shrink-0 rounded-xl bg-accent-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-400"
            >
              {copied ? 'Скопировано!' : 'Скопировать ссылку'}
            </button>
          </div>
        </Card>
      );
    }

    if (variant === 'global' || variant === 'compact') {
      return (
        <AnimatePresence>
          <motion.div
            initial={{ opacity: 0, y: variant === 'global' ? -20 : 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: variant === 'global' ? -20 : 10 }}
            transition={{ duration: 0.3 }}
            className={
              variant === 'global'
                ? "bg-accent-500/10 px-4 py-3 border-b border-accent-500/20"
                : "relative rounded-xl border border-accent-500/30 bg-accent-500/10 p-3"
            }
          >
            {variant === 'compact' && (
              <button
                onClick={dismissInstall}
                className="absolute right-2 top-2 rounded-lg p-1 text-accent-500/70 transition-colors hover:text-accent-400"
              >
                <CloseIcon />
              </button>
            )}
            
            <div className={`flex items-center gap-3 ${variant === 'global' ? 'max-w-6xl mx-auto' : 'pr-6'}`}>
              <div className="shrink-0 text-accent-400"><BrowserIcon /></div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-dark-100">Установите приложение</p>
                <p className="mt-0.5 text-xs text-dark-400">
                  Для установки откройте кабинет в системном браузере (Safari / Chrome)
                </p>
              </div>
              <button
                onClick={copyUrl}
                className="shrink-0 whitespace-nowrap text-xs font-medium text-accent-400 transition-colors hover:text-accent-300"
              >
                {copied ? 'Скопировано' : 'Копировать'}
              </button>
              
              {variant === 'global' && (
                <button onClick={dismissInstall} className="ml-2 text-dark-400 hover:text-dark-200">
                  <CloseIcon />
                </button>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
      );
    }
  }

  // === ОПРЕДЕЛЕНИЕ МАНУАЛЬНОГО РЕЖИМА УСТАНОВКИ ===
  const userAgent = window.navigator.userAgent.toLowerCase();
  
  // Детекция Chromium-браузеров (Chrome, Edge, Samsung Internet, etc.)
  const isChromium = /chrome|crios|crmo|edge|edg/i.test(userAgent) && !/otherview|opr|opera|firefox|iceweasel/i.test(userAgent);
  // Детекция Firefox
  const isFirefox = /firefox|iceweasel/i.test(userAgent);
  // Детекция Android
  const isAndroid = /android/i.test(userAgent);

  // Контент для iOS инструкции
  const iosContent = (
    <div className={`flex ${variant === 'card' ? 'items-start' : 'items-center'} gap-3`}>
      <div className={`${variant === 'card' ? 'mt-0.5' : 'shrink-0'} text-accent-400`}><PhoneIcon /></div>
      <div className="min-w-0 flex-1">
        <p className={`${variant === 'card' ? 'font-medium text-dark-100' : 'text-sm font-medium text-dark-200'}`}>
          {t('pwa.installTitle')}
        </p>
        {variant === 'card' ? (
          <>
            <p className="mt-1 text-sm text-dark-400">{t('pwa.installDesc')}</p>
            <div className="mt-3 space-y-2 text-sm text-dark-300">
              <p>1. {t('pwa.ios.step1')} <ShareIcon /></p>
              <p>2. {t('pwa.ios.step2')}</p>
              <p>3. {t('pwa.ios.step3')}</p>
            </div>
          </>
        ) : (
          <p className="mt-0.5 text-xs text-dark-400">
            {t('pwa.ios.compactHint')} <ShareIcon /> → {t('pwa.ios.step2Short')}
          </p>
        )}
      </div>
    </div>
  );

  // Контент для ручной установки Chrome/Chromium
  const chromiumManualContent = (
    <div className={`flex ${variant === 'card' ? 'items-start' : 'items-center'} gap-3`}>
      <div className={`${variant === 'card' ? 'mt-0.5' : 'shrink-0'} text-accent-400`}><PhoneIcon /></div>
      <div className="min-w-0 flex-1">
        <p className={`${variant === 'card' ? 'font-medium text-dark-100' : 'text-sm font-medium text-dark-200'}`}>
          Установка через меню Chrome
        </p>
        {variant === 'card' ? (
          <>
            <p className="mt-1 text-sm text-dark-400">
              Если кнопка установки не отображается (например, после недавнего удаления), вы можете установить приложение вручную:
            </p>
            <div className="mt-3 space-y-2 text-sm text-dark-300 pl-4 border-l border-dark-700/50">
              {isAndroid ? (
                <>
                  <p>1. Нажмите на три точки <span className="font-bold text-accent-400">(⋮)</span> в верхнем правом углу Chrome.</p>
                  <p>2. Выберите <span className="font-semibold text-dark-100">«Добавить на главный экран»</span> или <span className="font-semibold text-dark-100">«Установить приложение»</span>.</p>
                </>
              ) : (
                <>
                  <p>1. Нажмите на значок установки (плюс в круге/квадрате) в правой части адресной строки Chrome.</p>
                  <p>2. Либо нажмите на три точки <span className="font-bold text-accent-400">(⋮)</span> в правом верхнем углу и выберите <span className="font-semibold text-dark-100">«Установить»</span>.</p>
                </>
              )}
            </div>
          </>
        ) : (
          <p className="mt-0.5 text-xs text-dark-400">
            Нажмите на меню Chrome <span className="font-bold text-accent-400">(⋮)</span> → <span className="font-semibold">{isAndroid ? '«Добавить на гл. экран»' : '«Установить»'}</span>
          </p>
        )}
      </div>
    </div>
  );

  // Контент для ручной установки Firefox
  const firefoxManualContent = (
    <div className={`flex ${variant === 'card' ? 'items-start' : 'items-center'} gap-3`}>
      <div className={`${variant === 'card' ? 'mt-0.5' : 'shrink-0'} text-accent-400`}><PhoneIcon /></div>
      <div className="min-w-0 flex-1">
        <p className={`${variant === 'card' ? 'font-medium text-dark-100' : 'text-sm font-medium text-dark-200'}`}>
          Установка в Firefox
        </p>
        {variant === 'card' ? (
          <>
            <p className="mt-1 text-sm text-dark-400">
              Вы можете установить приложение вручную через настройки Firefox:
            </p>
            <div className="mt-3 space-y-2 text-sm text-dark-300 pl-4 border-l border-dark-700/50">
              <p>1. Нажмите на меню из трех точек <span className="font-bold text-accent-400">(⋮)</span> в углу экрана Firefox.</p>
              <p>2. Выберите пункт <span className="font-semibold text-dark-100">«Установить»</span> или <span className="font-semibold text-dark-100">«Добавить на главный экран»</span>.</p>
            </div>
          </>
        ) : (
          <p className="mt-0.5 text-xs text-dark-400">
            Нажмите на меню Firefox <span className="font-bold text-accent-400">(⋮)</span> → <span className="font-semibold">«Установить»</span>
          </p>
        )}
      </div>
    </div>
  );

  // Контент для других браузеров (generic)
  const genericManualContent = (
    <div className="flex items-start gap-3">
      <div className="text-accent-400 shrink-0 mt-0.5"><PhoneIcon /></div>
      <div className="min-w-0 flex-1">
        <p className="font-medium text-dark-100">
          Установка приложения
        </p>
        <p className="mt-1 text-sm text-dark-400">
          Вы можете запустить кабинет как приложение! Откройте меню настроек вашего браузера и выберите <span className="font-semibold text-dark-100">«Добавить на главный экран»</span> или <span className="font-semibold text-dark-100">«Установить»</span> для быстрого доступа.
        </p>
      </div>
    </div>
  );

  // Контент для Android/PC (нативная кнопка)
  const androidContent = (
    <>
      <div className="flex items-center gap-3 min-w-0">
        <div className="text-accent-400 shrink-0"><PhoneIcon /></div>
        <div className="min-w-0">
          <p className={`${variant === 'card' ? 'font-medium text-dark-100' : 'text-sm font-medium text-dark-200'}`}>
            {t('pwa.installTitle')}
          </p>
          {variant === 'card' && (
            <p className="text-sm text-dark-400">{t('pwa.installDesc')}</p>
          )}
        </div>
      </div>
      <button
        onClick={promptInstall}
        className={variant === 'card'
          ? "shrink-0 rounded-xl bg-accent-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-400 mt-3 sm:mt-0"
          : "shrink-0 text-xs font-medium text-accent-400 transition-colors hover:text-accent-300 ml-auto"
        }
      >
        {t('pwa.installButton')} {variant !== 'card' && '→'}
      </button>
    </>
  );

  // Выбор контента на основе доступности нативного промпта и типа браузера
  const renderPWAContent = () => {
    if (canInstall) {
      return androidContent;
    }
    // Если нативного промпта нет, используем ручные инструкции
    if (isIOS) return iosContent;
    if (isChromium) return chromiumManualContent;
    if (isFirefox) return firefoxManualContent;
    return genericManualContent;
  };

  // Решение о показе баннера в ручном режиме (для компактных вариантов)
  // Показываем компактный баннер ручной установки только на iOS, Chrome/Chromium и Firefox
  const canShowCompact = canInstall || isIOS || isChromium || isFirefox;

  // Регуляция рендеринга для карточки профиля
  if (variant === 'card') {
    return (
      <Card>
        <h2 className="mb-4 text-lg font-semibold text-dark-100">{t('pwa.sectionTitle')}</h2>
        <div className={`rounded-xl border border-accent-500/20 bg-accent-500/5 p-4 ${canInstall && !isIOS ? 'flex flex-col sm:flex-row sm:items-center justify-between gap-3' : ''}`}>
          {renderPWAContent()}
        </div>
      </Card>
    );
  }

  // Если ручная установка в компактном баннере нецелесообразна для данного браузера — скрываем
  if (!canShowCompact) {
    return null;
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: variant === 'global' ? -20 : 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: variant === 'global' ? -20 : 10 }}
        transition={{ duration: 0.3 }}
        className={
          variant === 'global'
            ? "bg-dark-800/90 px-4 py-3 border-b border-dark-700/50 backdrop-blur-md"
            : "relative rounded-xl border border-dark-700/50 bg-dark-800/80 p-3"
        }
      >
        <div className={`flex items-center ${variant === 'global' ? 'max-w-6xl mx-auto' : 'pr-6'}`}>
          {renderPWAContent()}
          
          <button
            onClick={dismissInstall}
            className={variant === 'global' 
              ? "ml-4 p-1 text-dark-400 hover:text-dark-200 shrink-0" 
              : "absolute right-2 top-2 rounded-lg p-1 text-dark-500 transition-colors hover:text-dark-300"}
          >
            <CloseIcon />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
