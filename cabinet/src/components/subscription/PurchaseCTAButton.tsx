import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
// Импортируем хук useQuery для выполнения запроса к API подарков
import { useQuery } from '@tanstack/react-query';
import { HoverBorderGradient } from '../ui/hover-border-gradient';
import type { Subscription } from '../../types';
// Импортируем giftApi для получения актуальной конфигурации подарков
import { giftApi } from '../../api/gift';

interface PurchaseCTAButtonProps {
  subscription: Subscription | null;
  /** В режиме мультитарифов ссылка ведет на продление конкретной подписки вместо общей покупки */
  isMultiTariff?: boolean;
}

export default function PurchaseCTAButton({
  subscription,
  isMultiTariff = false,
}: PurchaseCTAButtonProps) {
  const { t } = useTranslation();

  // Проверяем, истекла ли подписка или она отсутствует вообще
  const isExpired = !subscription || (!subscription.is_active && !subscription.is_trial);
  const isTrial = subscription?.is_trial;
  const isDaily = subscription?.is_daily;

  // Запрашиваем конфигурацию подарков, чтобы проверить, включена ли эта функция администратором
  const { data: giftConfig, isLoading: isGiftConfigLoading } = useQuery({
    queryKey: ['gift-config'],
    queryFn: giftApi.getConfig,
    staleTime: 30_000, // Кэшируем конфигурацию на 30 секунд
  });

  // Определяем, включен ли режим подарков
  const isGiftsEnabled = giftConfig?.is_enabled ?? false;

  // Обязательное логирование состояния рендеринга и доступности подарков (Правило 2)
  console.log(
    `[PurchaseCTAButton] Rendering. Subscription ID: ${subscription?.id || 'None'}, Expired: ${isExpired}, Gifts Enabled by Admin: ${isGiftsEnabled}, Config Loading: ${isGiftConfigLoading}`
  );

  // Тарифы с посуточной оплатой продлеваются автоматически, ручная кнопка продления в мультитарифе им не нужна
  if (isMultiTariff && isDaily && !isExpired) {
    // Но если подарки включены, мы всё равно хотим показать кнопку подарка!
    // В таком случае, если основная кнопка возвращает null, мы отрендерим только кнопку подарка.
    if (isGiftsEnabled) {
      console.log('[PurchaseCTAButton] Rendering only Gift button because daily tariff is active.');
      return (
        <div className="flex flex-col gap-3">
          <Link to="/gift" className="block">
            <HoverBorderGradient
              accentColor="rgb(var(--color-accent-400))"
              duration={4}
              className="group relative w-full cursor-pointer overflow-hidden rounded-2xl"
            >
              <div
                className="relative flex items-center justify-between rounded-[14px] px-5 py-4 transition-colors duration-300"
                style={{
                  background: 'linear-gradient(135deg, rgba(var(--color-accent-400), 0.08), rgba(var(--color-accent-400), 0.06))',
                }}
              >
                <div className="flex items-center gap-3">
                  {/* Красивая иконка подарка */}
                  <div
                    className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl"
                    style={{
                      background: 'rgba(var(--color-accent-400), 0.12)',
                    }}
                  >
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="rgb(var(--color-accent-400))"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <rect x="3" y="8" width="18" height="4" rx="1" />
                      <rect x="5" y="12" width="14" height="8" rx="1" />
                      <line x1="12" y1="8" x2="12" y2="20" />
                      <path d="M12 8c-2-2-4-3-5-2s0 3 2 4h3" />
                      <path d="M12 8c2-2 4-3 5-2s0 3-2 4h-3" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-[15px] font-semibold text-dark-50">
                      {t('gift.title', 'Подарить подписку')}
                    </div>
                    <div className="text-[12px] text-dark-50/40">
                      {t('gift.subtitle', 'Отправьте VPN-подписку в подарок')}
                    </div>
                  </div>
                </div>

                {/* Шеврон с анимацией сдвига при наведении */}
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className="flex-shrink-0 text-dark-50/30 transition-transform duration-300 group-hover:translate-x-1"
                >
                  <path d="M9 18l6-6-6-6" />
                </svg>
              </div>
            </HoverBorderGradient>
          </Link>
        </div>
      );
    }
    return null;
  }

  // Цвет акцента для кнопки: красный для истекшей, фиолетовый/акцентный для активной
  const accentColor = isExpired ? '#FF3B5C' : 'rgb(var(--color-accent-400))';

  // Текст кнопки продления/покупки
  const buttonText = isExpired
    ? t('subscription.getSubscription')
    : isTrial
      ? t('subscription.trialUpgrade.title')
      : t('subscription.extend');

  // Описание (подсказка) под главным текстом кнопки
  const hintText = isExpired
    ? t('subscription.cta.expiredHint')
    : isTrial
      ? t('subscription.cta.trialHint')
      : isMultiTariff
        ? t('subscription.cta.renewHint', 'Продление подписки')
        : t('subscription.cta.activeHint');

  // Путь перенаправления: триал -> покупка, мультитариф -> продление конкретной подписки, иначе -> покупка
  const linkTo = isTrial
    ? '/subscription/purchase'
    : isMultiTariff && subscription?.id
      ? `/subscriptions/${subscription.id}/renew`
      : '/subscription/purchase';

  return (
    <div className="flex flex-col gap-3">
      {/* Основная кнопка: Продлить / Купить тариф */}
      <Link to={linkTo} className="block">
        <HoverBorderGradient
          accentColor={accentColor}
          duration={4}
          className="group relative w-full cursor-pointer overflow-hidden rounded-2xl"
        >
          <div
            className="relative flex items-center justify-between rounded-[14px] px-5 py-4 transition-colors duration-300"
            style={{
              background: isExpired
                ? 'linear-gradient(135deg, rgba(255,59,92,0.08), rgba(255,107,53,0.06))'
                : 'linear-gradient(135deg, rgba(var(--color-accent-400), 0.08), rgba(var(--color-accent-400), 0.06))',
            }}
          >
            {/* Левая часть: иконка искры + тексты */}
            <div className="flex items-center gap-3">
              <div
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl"
                style={{
                  background: isExpired
                    ? 'rgba(255,59,92,0.12)'
                    : 'rgba(var(--color-accent-400), 0.12)',
                }}
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke={accentColor}
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                </svg>
              </div>
              <div>
                <div className="text-[15px] font-semibold text-dark-50">{buttonText}</div>
                <div className="text-[12px] text-dark-50/40">{hintText}</div>
              </div>
            </div>

            {/* Правая часть: шеврон стрелки с анимацией сдвига */}
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className="flex-shrink-0 text-dark-50/30 transition-transform duration-300 group-hover:translate-x-1"
            >
              <path d="M9 18l6-6-6-6" />
            </svg>
          </div>
        </HoverBorderGradient>
      </Link>

      {/* Условный рендеринг кнопки «Подарить подписку» при включенной в админке функции подарков */}
      {isGiftsEnabled && (
        <Link to="/gift" className="block">
          <HoverBorderGradient
            accentColor="rgb(var(--color-accent-400))"
            duration={4}
            className="group relative w-full cursor-pointer overflow-hidden rounded-2xl"
          >
            <div
              className="relative flex items-center justify-between rounded-[14px] px-5 py-4 transition-colors duration-300"
              style={{
                background: 'linear-gradient(135deg, rgba(var(--color-accent-400), 0.08), rgba(var(--color-accent-400), 0.06))',
              }}
            >
              {/* Левая часть: иконка подарка + тексты (из локализации) */}
              <div className="flex items-center gap-3">
                <div
                  className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl"
                  style={{
                    background: 'rgba(var(--color-accent-400), 0.12)',
                  }}
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="rgb(var(--color-accent-400))"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <rect x="3" y="8" width="18" height="4" rx="1" />
                    <rect x="5" y="12" width="14" height="8" rx="1" />
                    <line x1="12" y1="8" x2="12" y2="20" />
                    <path d="M12 8c-2-2-4-3-5-2s0 3 2 4h3" />
                    <path d="M12 8c2-2 4-3 5-2s0 3-2 4h-3" />
                  </svg>
                </div>
                <div>
                  <div className="text-[15px] font-semibold text-dark-50">
                    {t('gift.title', 'Подарить подписку')}
                  </div>
                  <div className="text-[12px] text-dark-50/40">
                    {t('gift.subtitle', 'Отправьте VPN-подписку в подарок')}
                  </div>
                </div>
              </div>

              {/* Правая часть: шеврон стрелки с анимацией сдвига */}
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                className="flex-shrink-0 text-dark-50/30 transition-transform duration-300 group-hover:translate-x-1"
              >
                <path d="M9 18l6-6-6-6" />
              </svg>
            </div>
          </HoverBorderGradient>
        </Link>
      )}
    </div>
  );
}

