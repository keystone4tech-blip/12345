import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';

/**
 * Хук для управления позицией скролла (прокрутки) при переходах между страницами.
 * Сохраняет и восстанавливает скролл для страниц панели администратора,
 * и автоматически сбрасывает прокрутку в самый верх (y = 0) для всех страниц личного кабинета.
 */
export function useScrollRestoration() {
  const location = useLocation();
  const scrollPositions = useRef<Record<string, number>>({});

  // Отключаем встроенное в браузер автоматическое восстановление прокрутки
  useEffect(() => {
    if ('scrollRestoration' in history) {
      history.scrollRestoration = 'manual';
    }
  }, []);

  // Управление скроллом при изменении роута (pathname)
  useEffect(() => {
    const currentPath = location.pathname;

    // Для административных страниц (/admin) — сохраняем и восстанавливаем позицию
    if (currentPath.startsWith('/admin')) {
      const handleScroll = () => {
        scrollPositions.current[currentPath] = window.scrollY;
      };

      // Слушаем прокрутку для сохранения текущей координаты
      window.addEventListener('scroll', handleScroll, { passive: true });

      const savedPosition = scrollPositions.current[currentPath];
      if (savedPosition !== undefined && savedPosition > 0) {
        window.scrollTo({ top: savedPosition, behavior: 'instant' });
      } else {
        window.scrollTo({ top: 0, behavior: 'instant' });
      }

      return () => {
        window.removeEventListener('scroll', handleScroll);
      };
    } else {
      // Для всех остальных клиентских страниц личного кабинета — всегда сбрасываем скролл в самый верх
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, [location.pathname]);
}

