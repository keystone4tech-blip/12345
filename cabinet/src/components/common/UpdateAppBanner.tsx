// @ts-ignore
import { useRegisterSW } from 'virtual:pwa-register/react';

export default function UpdateAppBanner() {
  // hook from vite-plugin-pwa that handles the SW update lifecycle
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegistered(r: any) {
      // Periodically check for updates every hour if the app stays open
      if (r) {
        setInterval(() => {
          r.update();
        }, 60 * 60 * 1000);
      }
    },
    onRegisterError(error: any) {
      console.error('SW registration error', error);
    },
  });

  if (!needRefresh) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[9999] p-4 bg-dark-800 border border-accent-500 rounded-2xl shadow-xl max-w-xs animate-in slide-in-from-bottom-5">
      <h3 className="text-white font-semibold mb-1">Доступно обновление</h3>
      <p className="text-dark-300 text-sm mb-4">
        Установлена новая версия приложения с обновленными функциями и логотипом. Обновите для применения.
      </p>
      <div className="flex gap-2">
        <button 
          onClick={() => updateServiceWorker(true)}
          className="flex-1 px-4 py-2 bg-accent-500 text-white rounded-lg text-sm font-medium hover:bg-accent-600 transition"
        >
          Обновить
        </button>
        <button 
          onClick={() => setNeedRefresh(false)}
          className="px-4 py-2 bg-dark-700 text-white rounded-lg text-sm font-medium hover:bg-dark-600 transition"
        >
          Позже
        </button>
      </div>
    </div>
  );
}
