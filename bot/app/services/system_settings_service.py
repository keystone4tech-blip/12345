import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional, Union, get_args, get_origin

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    ENV_OVERRIDE_KEYS,
    Settings,
    refresh_period_prices,
    refresh_traffic_prices,
    settings,
)
from app.database.crud.system_setting import (
    delete_system_setting,
    upsert_system_setting,
)
from app.database.database import AsyncSessionLocal
from app.database.models import SystemSetting
from app.services.web_api_token_service import ensure_default_web_api_token


logger = structlog.get_logger(__name__)


def _title_from_key(key: str) -> str:
    parts = key.split('_')
    if not parts:
        return key
    return ' '.join(part.capitalize() for part in parts)


def _truncate(value: str, max_len: int = 60) -> str:
    value = value.strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + '…'


@dataclass(slots=True)
class SettingDefinition:
    key: str
    category_key: str
    category_label: str
    python_type: type[Any]
    type_label: str
    is_optional: bool

    @property
    def display_name(self) -> str:
        # Сначала проверяем наличие понятного названия в словаре перевода
        if self.key in BotConfigurationService.SETTING_LABELS:
            return BotConfigurationService.SETTING_LABELS[self.key]
            
        # Если перевода нет, генерируем из ключа (старая логика)
        return _title_from_key(self.key)


@dataclass(slots=True)
class ChoiceOption:
    value: Any
    label: str
    description: str | None = None


class ReadOnlySettingError(RuntimeError):
    """Исключение, выбрасываемое при попытке изменить настройку только для чтения."""


class BotConfigurationService:
    EXCLUDED_KEYS: set[str] = {'BOT_TOKEN', 'ADMIN_IDS'}

    READ_ONLY_KEYS: set[str] = {'EXTERNAL_ADMIN_TOKEN', 'EXTERNAL_ADMIN_TOKEN_BOT_ID'}
    PLAIN_TEXT_KEYS: set[str] = {'EXTERNAL_ADMIN_TOKEN', 'EXTERNAL_ADMIN_TOKEN_BOT_ID'}

    CATEGORY_TITLES: dict[str, str] = {
        'CORE': '🤖 Основные настройки',
        'SUPPORT': '💬 Поддержка и тикеты',
        'LOCALIZATION': '🌍 Языки интерфейса',
        'CHANNEL': '📣 Обязательная подписка',
        'TIMEZONE': '🗂 Timezone',
        'PAYMENT': '💳 Общие платежные настройки',
        'PAYMENT_VERIFICATION': '🕵️ Проверка платежей',
        'TELEGRAM': '⭐ Telegram Stars',
        'CRYPTOBOT': '🪙 CryptoBot',
        'HELEKET': '🪙 Heleket',
        'CLOUDPAYMENTS': '💳 CloudPayments',
        'FREEKASSA': '💳 Freekassa',
        'KASSA_AI': '💳 KassaAI',
        'YOOKASSA': '🟣 YooKassa',
        'PLATEGA': '💳 {platega_name}',
        'TRIBUTE': '🎁 Tribute',
        'MULENPAY': '💰 {mulenpay_name}',
        'PAL24': '🏦 PAL24 / PayPalych',
        'WATA': '💠 Wata',
        'EXTERNAL_ADMIN': '🛡️ Внешняя админка',
        'SUBSCRIPTIONS_CORE': '📅 Подписки и лимиты',
        'SIMPLE_SUBSCRIPTION': '⚡ Простая покупка',
        'PERIODS': '📆 Периоды подписок',
        'SUBSCRIPTION_PRICES': '💵 Стоимость тарифов',
        'TRAFFIC': '📊 Трафик',
        'TRAFFIC_PACKAGES': '📦 Пакеты трафика',
        'TRIAL': '🎁 Пробный период',
        'REFERRAL': '👥 Реферальная программа',
        'AUTOPAY': '🔄 Автопродление',
        'NOTIFICATIONS': '🔔 Уведомления пользователям',
        'ADMIN_NOTIFICATIONS': '📣 Оповещения администраторам',
        'ADMIN_REPORTS': '🗂 Автоматические отчеты',
        'INTERFACE': '🎨 Интерфейс и брендинг',
        'INTERFACE_BRANDING': '🖼️ Брендинг',
        'INTERFACE_SUBSCRIPTION': '🔗 Ссылка на подписку',
        'CONNECT_BUTTON': '🚀 Кнопка подключения',
        'MINIAPP': '📱 Mini App',
        'HAPP': '🅷 Happ',
        'SKIP': '⚡ Быстрый старт',
        'ADDITIONAL': '📱 Дополнительные приложения',
        'DATABASE': '💾 База данных',
        'POSTGRES': '🐘 PostgreSQL',
        'SQLITE': '🧱 SQLite',
        'REDIS': '🧠 Redis',
        'REMNAWAVE': '🌐 RemnaWave API',
        'SERVER_STATUS': '📊 Статус серверов',
        'MONITORING': '📈 Мониторинг',
        'MAINTENANCE': '🔧 Обслуживание',
        'BACKUP': '💾 Резервные копии',
        'VERSION': '🔄 Проверка версий',
        'WEB_API': '⚡ Web API',
        'WEBHOOK': '🌐 Webhook',
        'WEBHOOK_NOTIFICATIONS': '📢 Уведомления от вебхуков',
        'LOG': '📝 Логирование',
        'DEBUG': '🧪 Режим разработки',
        'MODERATION': '🛡️ Модерация и фильтры',
        'BAN_NOTIFICATIONS': '🚫 Тексты уведомлений о блокировках',
        'SUPPORT_AI': '🤖 DonMatteo-AI-Tiket',
        'GIFTS': '🎁 Система подарков',
        'NALOGO': '🧾 NaloGO (Самозанятые)',
    }

    SETTING_LABELS: dict[str, str] = {
        # CORE
        'BOT_USERNAME': '🤖 Юзернейм бота',
        'SUPPORT_USERNAME': '💬 Контакт поддержки',
        'MAINTENANCE_MODE': '🔧 Режим тех. работ',
        'MAINTENANCE_MESSAGE': '📝 Текст заглушки тех. работ',
        'MAINTENANCE_CHECK_INTERVAL': '⏱ Интервал проверок (сек)',
        'MAINTENANCE_AUTO_ENABLE': '🤖 Авто-включение при сбоях',
        'MAINTENANCE_MONITORING_ENABLED': '📡 Мониторинг доступности',
        'BOT_RUN_MODE': '🚀 Режим запуска (polling/webhook)',
        'EXTERNAL_ADMIN_TOKEN': '🛡️ Токен внешней админки',
        'EXTERNAL_ADMIN_TOKEN_BOT_ID': '🆔 ID бота для внеш. админки',
        'ACTIVATE_BUTTON_VISIBLE': '🔘 Показать кнопку активации',
        'ACTIVATE_BUTTON_TEXT': '🔘 Текст кнопки активации',
        'SKIP_REFERRAL_CODE': '⏩ Пропустить ввод реф-кода',
        'SKIP_RULES_ACCEPT': '⏩ Пропустить принятие правил',
        'ADMIN_EMAILS': '📧 Email-адреса администраторов',
        'TEST_EMAIL': '🧪 Тестовый Email',
        'TEST_EMAIL_PASSWORD': '🔑 Пароль тестового Email',
        'DEBUG': '🧪 Режим отладки (логирование)',
        'SERVER_STATUS_MODE': '📊 Режим статуса серверов',
        'SERVER_STATUS_EXTERNAL_URL': '🌐 Внешняя ссылка статуса',
        'SERVER_STATUS_METRICS_URL': '📈 URL метрик (Prometheus)',
        'SERVER_STATUS_METRICS_USERNAME': '👤 Метрики: Логин',
        'SERVER_STATUS_METRICS_PASSWORD': '🔑 Метрики: Пароль',
        'SERVER_STATUS_REQUEST_TIMEOUT': '⏱ Тайм-аут запросов статуса',

        # SUPPORT
        'SUPPORT_MENU_ENABLED': 'Включить меню поддержки',
        'SUPPORT_SYSTEM_MODE': 'Режим системы поддержки',
        'SUPPORT_TICKET_SLA_ENABLED': 'Включить SLA для тикетов',
        'SUPPORT_TICKET_SLA_MINUTES': 'SLA: время ответа (мин)',
        'SUPPORT_TICKET_SLA_CHECK_INTERVAL_SECONDS': 'SLA: интервал проверки (сек)',
        'SUPPORT_TICKET_SLA_REMINDER_COOLDOWN_MINUTES': 'SLA: интервал напоминаний (мин)',
        'SUPPORT_AI_ENABLED': 'Включить AI-помощника',
        'SUPPORT_AI_FORUM_ID': 'ID темы на форуме для ИИ',
        'MINIAPP_TICKETS_ENABLED': 'Тикеты в MiniApp',

        # REFERRAL
        'REFERRAL_PROGRAM_ENABLED': 'Включить реферальную программу',
        'REFERRAL_PARTNER_SECTION_VISIBLE': 'Показывать раздел в кабинете',
        'REFERRAL_COMMISSION_PERCENT': 'Процент вознаграждения (%)',
        'REFERRAL_INVITER_BONUS_KOPEKS': 'Бонус за приглашение (коп)',
        'REFERRAL_FIRST_TOPUP_BONUS_KOPEKS': 'Бонус рефералу за 1-е пополнение',
        'REFERRAL_MINIMUM_TOPUP_KOPEKS': 'Мин. пополнение для бонуса',
        'REFERRAL_NOTIFICATIONS_ENABLED': 'Уведомления о новых рефералах',
        'REFERRAL_BUTTON_TEXT': 'Текст кнопки партнерки',
        'REFERRAL_BUTTON_STYLE': 'Цвет кнопки партнерки',
        'REFERRAL_BUTTON_EMOJI': 'Премиум-эмодзи кнопки',
        'REFERRAL_WITHDRAWAL_ENABLED': 'Разрешить вывод средств',
        'REFERRAL_WITHDRAWAL_MIN_AMOUNT_KOPEKS': 'Мин. сумма для вывода',
        'REFERRAL_WITHDRAWAL_COOLDOWN_DAYS': 'Задержка между выводами (дней)',
        'REFERRAL_CONTESTS_ENABLED': 'Включить конкурсы рефералов',
        'CONTESTS_ENABLED': 'Глобальный флаг конкурсов',
        'CONTESTS_BUTTON_VISIBLE': 'Показывать кнопку конкурсов в меню',

        # REFERRAL - FRAUD PROTECTION
        'REFERRAL_WITHDRAWAL_SUSPICIOUS_MIN_DEPOSIT_KOPEKS': 'Анти-фрод: Мин. пополнение для вывода',
        'REFERRAL_WITHDRAWAL_SUSPICIOUS_MAX_DEPOSITS_PER_MONTH': 'Анти-фрод: Макс. депозитов в месяц',
        'REFERRAL_WITHDRAWAL_SUSPICIOUS_NO_PURCHASES_RATIO': 'Анти-фрод: Коэфф. подозрительных трат',
        'REFERRAL_WITHDRAWAL_ONLY_REFERRAL_BALANCE': 'Вывод только партнерского баланса',
        'REFERRAL_WITHDRAWAL_REQUISITES_TEXT': 'Инструкция по реквизитам при выводе',
        'REFERRAL_WITHDRAWAL_NOTIFICATIONS_TOPIC_ID': 'Топик заявок на вывод',
        'REFERRAL_WITHDRAWAL_TEST_MODE': 'Тестовый режим системы вывода',

        # GIFTS
        'GIFTS_ENABLED': 'Включить систему подарков',
        'GIFTS_BUTTON_VISIBLE': 'Кнопка «Подарок» в меню',
        'GIFTS_BUTTON_TEXT': 'Текст кнопки подарка',
        'GIFTS_BUTTON_STYLE': 'Цвет кнопки подарка',
        'GIFTS_BUTTON_EMOJI': 'Премиум-эмодзи кнопки',
        'GIFTS_SHARE_MESSAGE_TEMPLATE': 'Шаблон сообщения с подарком',

        # INTERFACE
        'MAIN_MENU_MODE': 'Стиль главного меню',
        'CABINET_BUTTON_STYLE': 'Общий цвет кнопок кабинета',
        'ENABLE_LOGO_MODE': '🖼️ Показывать логотип',
        'LOGO_FILE': '📁 Файл логотипа',
        'USE_PREMIUM_EMOJIS': '✨ Использовать Premium эмодзи',
        'PREMIUM_EMOJIS_DATA': '📊 Данные Premium эмодзи',
        'HIDE_SUBSCRIPTION_LINK': '🔗 Скрыть ссылки на подписку',

        # BRANDING & MINIAPP
        'MINIAPP_SERVICE_NAME_RU': 'Название сервиса (RU)',
        'MINIAPP_SERVICE_NAME_EN': 'Название сервиса (EN)',
        'MINIAPP_SERVICE_DESCRIPTION_RU': 'Описание сервиса (RU)',
        'MINIAPP_SERVICE_DESCRIPTION_EN': 'Описание сервиса (EN)',
        'MINIAPP_CUSTOM_URL': 'Кастомный URL MiniApp',
        'MINIAPP_PURCHASE_URL': 'URL покупки в MiniApp',
        'CONNECT_BUTTON_HAPP_DOWNLOAD_ENABLED': 'Кнопка загрузки Happ',
        'HAPP_DOWNLOAD_LINK_IOS': 'Happ: Ссылка iOS',
        'HAPP_DOWNLOAD_LINK_ANDROID': 'Happ: Ссылка Android',
        'HAPP_DOWNLOAD_LINK_WINDOWS': 'Happ: Ссылка Windows',
        'HAPP_DOWNLOAD_LINK_MACOS': 'Happ: Ссылка macOS',
        'HAPP_DOWNLOAD_LINK_PC': 'Happ: Ссылка PC (общая)',
        'MINIAPP_SUPPORT_TYPE': 'Тип поддержки (Tickets/Profile/URL)',
        'MINIAPP_SUPPORT_URL': 'Кастомная ссылка поддержки',

        # TRIAL
        'TRIAL_DURATION_DAYS': '⏳ Длительность триала (дней)',
        'TRIAL_TRAFFIC_LIMIT_GB': '📊 Лимит трафика триала (ГБ)',
        'TRIAL_DEVICE_LIMIT': '📱 Лимит устройств триала',
        'TRIAL_ACTIVATION_PRICE': '💰 Цена активации триала',
        'TRIAL_PAYMENT_ENABLED': '💳 Платная активация триала',
        'TRIAL_ADD_REMAINING_DAYS_TO_PAID': '📅 Перенос дней триала при покупке',
        'TRIAL_DISABLED_FOR': '🚫 Триал отключен для...',
        'TRIAL_WARNING_HOURS': '🔔 Предупреждение об окончании (ч)',
        'TRIAL_USER_TAG': '🏷️ Тег триал-пользователя (RemnaWave)',

        # SUBSCRIPTIONS
        'BASE_SUBSCRIPTION_PRICE': '💵 Базовая цена подписки',
        'DEFAULT_DEVICE_LIMIT': '📱 Лимит устройств по умолчанию',
        'DEFAULT_TRAFFIC_LIMIT_GB': '📊 Лимит трафика (ГБ)',
        'SALES_MODE': '📦 Режим продаж (Classic/Tariffs)',
        'DEVICES_SELECTION_ENABLED': '🔢 Выбор кол-ва устройств',
        'PRICE_PER_DEVICE': '💰 Цена за доп. устройство',
        'MAX_DEVICES_LIMIT': '🚫 Макс. кол-во устройств',

        # SYSTEM
        'TIMEZONE': '🌍 Часовой пояс',
        'LOG_LEVEL': '📝 Уровень логов',
        'AUTO_PURCHASE_AFTER_TOPUP_ENABLED': '🔄 Автопокупка после оплаты',
        'PRICE_ROUNDING_ENABLED': '🔢 Округление цен',
        'APP_CONFIG_CACHE_TTL': '🧠 TTL кэша конфига приложений',
        'DEFAULT_AUTOPAY_ENABLED': '🔄 Автопродление по умолчанию',
        'DEFAULT_AUTOPAY_DAYS_BEFORE': '⏳ Дней до оплаты (автопродление)',
        'MIN_BALANCE_FOR_AUTOPAY_KOPEKS': '💰 Мин. баланс для автопродления',
        'AUTOPAY_WARNING_DAYS': '🔔 Уведомлять об автопродлении за (дн)',

        # BACKUPS
        'BACKUP_AUTO_ENABLED': 'Включить авто-бэкапы',
        'BACKUP_TIME': 'Время создания бэкапа',
        'BACKUP_INTERVAL_HOURS': 'Интервал бэкапов (час)',
        'BACKUP_MAX_KEEP': 'Кол-во хранимых архивов',
        'BACKUP_COMPRESSION': 'Сжатие архивов (Zip)',
        'BACKUP_LOCATION': 'Путь к хранилищу бэкапов',
        'BACKUP_SEND_ENABLED': 'Отправлять бэкапы в Telegram',
        'BACKUP_SEND_CHAT_ID': 'ID чата для бэкапов',
        'BACKUP_SEND_TOPIC_ID': 'ID топика в чате бэкапов',
        'BACKUP_INCLUDE_LOGS': 'Включать логи в архив',
        'BACKUP_ARCHIVE_PASSWORD': '🛡️ Пароль архива бэкапа',

        # NOTIFICATIONS & TOPICS
        'ADMIN_NOTIFICATIONS_ENABLED': 'Включить уведомления админа',
        'ADMIN_NOTIFICATIONS_CHAT_ID': 'ID чата уведомлений',
        'ADMIN_NOTIFICATIONS_TICKET_TOPIC_ID': 'Топик для тикетов поддержки',
        'ADMIN_NOTIFICATIONS_NALOG_TOPIC_ID': 'Топик для чеков NaloGO',
        'SUSPICIOUS_NOTIFICATIONS_TOPIC_ID': 'Топик подозрительного трафика',
        'ADMIN_REPORTS_ENABLED': 'Включить автоматические отчеты',
        'ADMIN_REPORTS_CHAT_ID': 'ID чата для отчетов',
        'ADMIN_REPORTS_TOPIC_ID': 'ID топика для отчетов',
        'ADMIN_REPORTS_SEND_TIME': 'Время ежедневного отчета',

        # WEB API & CABINET
        'WEB_API_ENABLED': 'Включить Web API',
        'WEB_API_HOST': 'Web API: Хост',
        'WEB_API_PORT': 'Web API: Порт',
        'WEB_API_ALLOWED_ORIGINS': 'Web API: Разрешенные CORS',
        'WEB_API_DOCS_ENABLED': 'Web API: Swagger докс',
        'WEB_API_WORKERS': 'Web API: Кол-во воркеров',
        'WEB_API_TITLE': 'Web API: Заголовок',
        'WEB_API_VERSION': 'Web API: Версия',
        'WEB_API_DEFAULT_TOKEN': 'Web API: Дефолтный токен',
        'WEB_API_REQUEST_LOGGING': 'Web API: Логирование запросов',
        'CABINET_ENABLED': 'Включить Личный Кабинет',
        'CABINET_URL': 'URL Личного Кабинета',
        'CABINET_ALLOWED_ORIGINS': 'Разрешенные домены Кабинета',
        'CABINET_EMAIL_VERIFICATION_ENABLED': 'Подтверждение почты',
        'CABINET_ACCESS_TOKEN_EXPIRE_MINUTES': 'JWT: Время жизни (мин)',
        'CABINET_REFRESH_TOKEN_EXPIRE_DAYS': 'JWT: Время обновления (дни)',
        'CABINET_JWT_SECRET': 'JWT: Секретный ключ (Secret)',
        'CABINET_EMAIL_AUTH_ENABLED': 'Включить вход по Email',

        # SMTP & EMAILS
        'SMTP_HOST': 'SMTP: Хост',
        'SMTP_PORT': 'SMTP: Порт',
        'SMTP_USER': 'SMTP: Пользователь',
        'SMTP_PASSWORD': 'SMTP: Пароль',
        'SMTP_FROM_EMAIL': 'SMTP: Email отправителя',
        'SMTP_FROM_NAME': 'SMTP: Имя отправителя',
        'SMTP_USE_TLS': 'SMTP: Использовать TLS',

        # SUBSCRIPTIONS_CORE
        'BASE_SUBSCRIPTION_PRICE': '💵 Базовая цена подписки',
        'DEFAULT_DEVICE_LIMIT': '📱 Лимит устройств по умолчанию',
        'DEFAULT_TRAFFIC_LIMIT_GB': '📊 Лимит трафика (ГБ)',
        'SALES_MODE': '📦 Режим продаж (Classic/Tariffs)',
        'DEVICES_SELECTION_ENABLED': '🔢 Выбор кол-ва устройств',
        'PRICE_PER_DEVICE': '💰 Цена за доп. устройство',
        'MAX_DEVICES_LIMIT': '🚫 Макс. кол-во устройств',
        'FIXED_TRAFFIC_LIMIT_GB': 'Лимит трафика (фиксированный)',
        'BUY_SUBSCRIPTION_BUTTON_TEXT': 'Текст кнопки покупки',
        'BUY_SUBSCRIPTION_BUTTON_STYLE': 'Цвет кнопки покупки',
        'BUY_SUBSCRIPTION_BUTTON_EMOJI': 'Премиум-эмодзи кнопки покупки',
        'SUBSCRIPTION_BUTTON_TEXT': 'Текст раздела «Подписка»',
        'BUY_TRAFFIC_BUTTON_VISIBLE': 'Кнопка докупки трафика',

        # OAUTH
        'OAUTH_GOOGLE_ENABLED': 'Включить Google OAuth',
        'OAUTH_GOOGLE_CLIENT_ID': 'Google: Client ID',
        'OAUTH_GOOGLE_CLIENT_SECRET': 'Google: Client Secret',
        'OAUTH_YANDEX_ENABLED': 'Включить Yandex OAuth',
        'OAUTH_YANDEX_CLIENT_ID': 'Yandex: Client ID',
        'OAUTH_YANDEX_CLIENT_SECRET': 'Yandex: Client Secret',
        'OAUTH_DISCORD_ENABLED': 'Включить Discord OAuth',
        'OAUTH_DISCORD_CLIENT_ID': 'Discord: Client ID',
        'OAUTH_DISCORD_CLIENT_SECRET': 'Discord: Client Secret',
        'OAUTH_VK_ENABLED': 'Включить VK OAuth',
        'OAUTH_VK_CLIENT_ID': 'VK: Client ID',
        'OAUTH_VK_CLIENT_SECRET': 'VK: Client Secret',

        # UPDATES & SECURITY
        'BAN_SYSTEM_API_TOKEN': 'Токен бан-системы',
        'BAN_MSG_PUNISHMENT': 'Текст уведомления о бане',
        'BAN_MSG_ENABLED': 'Текст уведомления об активации',
        'BAN_MSG_WIFI': 'Текст бана за WiFi',
        'BAN_MSG_MOBILE': 'Текст бана за мобильную сеть',
        'BAN_MSG_WARNING': 'Текст общего предупреждения',
        'BLACKLIST_CHECK_ENABLED': 'Включить черный список (GitHub)',
        'BLACKLIST_GITHUB_URL': 'URL черного списка пользователей',
        'BLACKLIST_UPDATE_INTERVAL_HOURS': 'Интервал обновления списка (ч)',
        'BLACKLIST_IGNORE_ADMINS': 'Игнорировать админов в ЧС',
        'DISPLAY_NAME_BANNED_KEYWORDS': 'Запрещенные слова в именах',
        'DISPOSABLE_EMAIL_CHECK_ENABLED': 'Блокировка временных почт',
        'VERSION_CHECK_ENABLED': 'Проверка обновлений бота',

        # LOGS & ROTATION
        'LOG_ROTATION_ENABLED': 'Включить ротацию логов',
        'LOG_ROTATION_TIME': 'Время ротации (HH:MM)',
        'LOG_ROTATION_KEEP_DAYS': 'Хранить логов (дней)',
        'LOG_ROTATION_COMPRESS': 'Сжимать логи (Gzip)',
        'LOG_ROTATION_SEND_TO_TELEGRAM': 'Отправлять логи в Telegram',
        'LOG_ROTATION_CHAT_ID': 'ID чата для логов',
        'LOG_ROTATION_TOPIC_ID': 'ID топика логов',
        'LOG_DIR': 'Папка для журналов (logs)',
        'LOG_INFO_FILE': 'Файл INFO логов',
        'LOG_ERROR_FILE': 'Файл ERROR логов',
        'LOG_PAYMENTS_FILE': 'Файл PAYMENT логов',

        # DATABASE
        'DATABASE_MODE': 'Режим базы данных',
        'DATABASE_URL': 'Прямой URL базы данных',
        'POSTGRES_HOST': 'Хост PostgreSQL',
        'POSTGRES_PORT': 'Порт PostgreSQL',
        'POSTGRES_DB': 'Имя базы данных',
        'POSTGRES_USER': 'Пользователь PostgreSQL',
        'POSTGRES_PASSWORD': 'Пароль PostgreSQL',
        'SQLITE_PATH': 'Путь к файлу SQLite',
        'REDIS_URL': 'URL Redis',
        'LOCALES_PATH': 'Путь к файлам локализации',
        'CART_TTL_SECONDS': 'Время жизни корзины (сек)',

        # REMNAWAVE
        'REMNAWAVE_API_URL': 'URL API RemnaWave',
        'REMNAWAVE_API_KEY': 'API ключ (RemnaWave)',
        'REMNAWAVE_SECRET_KEY': 'Секретный ключ (RemnaWave)',
        'REMNAWAVE_USERNAME': 'Логин в панель RemnaWave',
        'REMNAWAVE_PASSWORD': 'Пароль в панель RemnaWave',
        'REMNAWAVE_AUTH_TYPE': 'Метод авторизации API',
        'REMNAWAVE_AUTO_SYNC_ENABLED': 'Автоматическая синхронизация',
        'REMNAWAVE_AUTO_SYNC_TIMES': 'График синхронизации (03:00, 15:00)',
        'REMNAWAVE_WEBHOOK_ENABLED': 'Вебхуки RemnaWave (real-time)',
        'REMNAWAVE_WEBHOOK_SECRET': 'Секрет вебхука (HMAC SHA-256)',

        # PAYMENTS - GENERAL
        'TELEGRAM_STARS_ENABLED': 'Включить Telegram Stars',
        'TELEGRAM_STARS_RATE_RUB': 'Курс Stars (в рублях)',
        'PRICE_ROUNDING_ENABLED': 'Округление цен',
        'PAYMENT_VERIFICATION_AUTO_CHECK_ENABLED': 'Автопроверка платежей',

        # TRAFFIC - ADVANCED
        'TRAFFIC_SELECTION_MODE': 'Режим выбора трафика',
        'TRAFFIC_FAST_CHECK_INTERVAL_MINUTES': 'Интервал быстрой проверки (мин)',
        'TRAFFIC_FAST_CHECK_THRESHOLD_GB': 'Порог быстрой проверки (ГБ)',
        'TRAFFIC_DAILY_CHECK_ENABLED': 'Включить суточную проверку',
        'TRAFFIC_DAILY_CHECK_TIME': 'Время суточной проверки',
        'TRAFFIC_DAILY_THRESHOLD_GB': 'Порог суточного трафика (ГБ)',
        'TRAFFIC_MONITORED_NODES': 'Список наблюдаемых нод',
        'TRAFFIC_IGNORED_NODES': 'Список игнорируемых нод',
        'DEFAULT_TRAFFIC_RESET_STRATEGY': 'Стратегия сброса трафика',
        'RESET_TRAFFIC_ON_PAYMENT': 'Сброс трафика при оплате',
        'RESET_TRAFFIC_ON_TARIFF_SWITCH': 'Сброс при смене тарифа',

        # PAYMENT TEMPLATES
        'PAYMENT_SERVICE_NAME': 'Название услуги в чеке',
        'PAYMENT_BALANCE_DESCRIPTION': 'Описание пополнения баланса',
        'PAYMENT_SUBSCRIPTION_DESCRIPTION': 'Описание оплаты подписки',
        'PAYMENT_BALANCE_TEMPLATE': 'Шаблон чека (Баланс)',
        'PAYMENT_SUBSCRIPTION_TEMPLATE': 'Шаблон чека (Подписка)',

        # PAYMENTS - YOOKASSA
        'YOOKASSA_ENABLED': 'Включить YooKassa',
        'YOOKASSA_SHOP_ID': 'YooKassa: Shop ID',
        'YOOKASSA_SECRET_KEY': 'YooKassa: Secret Key',
        'YOOKASSA_RETURN_URL': 'YooKassa: URL возврата',
        'YOOKASSA_DEFAULT_RECEIPT_EMAIL': 'YooKassa: Email для чеков',
        'YOOKASSA_VAT_CODE': 'YooKassa: Код НДС',
        'YOOKASSA_SBP_ENABLED': 'YooKassa: Включить СБП',
        'YOOKASSA_PAYMENT_MODE': 'YooKassa: Признак способа расчета',
        'YOOKASSA_PAYMENT_SUBJECT': 'YooKassa: Признак предмета расчета',
        'YOOKASSA_MIN_AMOUNT_KOPEKS': 'YooKassa: Мин. сумма пополнения',
        'YOOKASSA_MAX_AMOUNT_KOPEKS': 'YooKassa: Макс. сумма пополнения',
        'YOOKASSA_QUICK_AMOUNT_SELECTION_ENABLED': 'YooKassa: Быстрый выбор сумм',

        # PAYMENTS - CRYPTOBOT
        'CRYPTOBOT_ENABLED': 'Включить CryptoBot',
        'CRYPTOBOT_API_TOKEN': 'CryptoBot: API Токен',
        'CRYPTOBOT_WEBHOOK_SECRET': 'CryptoBot: Секрет вебхука',
        'CRYPTOBOT_TESTNET': 'CryptoBot: Тестовая сеть (Testnet)',
        'CRYPTOBOT_DEFAULT_ASSET': 'CryptoBot: Валюта по умолчанию',
        'CRYPTOBOT_ASSETS': 'CryptoBot: Доступные валюты',
        'CRYPTOBOT_INVOICE_EXPIRES_HOURS': 'CryptoBot: Срок жизни счета (ч)',

        # PAYMENTS - FREEKASSA / KASSA.AI
        'FREEKASSA_ENABLED': 'Включить Freekassa',
        'FREEKASSA_SHOP_ID': 'Freekassa: ID магазина',
        'FREEKASSA_API_KEY': 'Freekassa: API ключ',
        'FREEKASSA_SECRET_WORD_1': 'Freekassa: Секретное слово 1',
        'FREEKASSA_SECRET_WORD_2': 'Freekassa: Секретное слово 2',
        'FREEKASSA_SBP_ENABLED': 'Freekassa: Включить СБП',
        'FREEKASSA_CARD_ENABLED': 'Freekassa: Включить Карты РФ',
        'KASSA_AI_ENABLED': 'Включить KassaAI',
        'KASSA_AI_SHOP_ID': 'KassaAI: ID магазина',
        'KASSA_AI_API_KEY': 'KassaAI: API ключ',
        'KASSA_AI_SECRET_WORD_2': 'KassaAI: Секретное слово 2',

        # PAYMENTS - PAL24
        'PAL24_ENABLED': 'Включить PayPalych (PAL24)',
        'PAL24_API_TOKEN': 'PAL24: API Токен',
        'PAL24_SHOP_ID': 'PAL24: Shop ID',
        'PAL24_SIGNATURE_TOKEN': 'PAL24: Секрет подписи',
        'PAL24_SBP_BUTTON_VISIBLE': 'PAL24: Показать кнопку СБП',
        'PAL24_CARD_BUTTON_VISIBLE': 'PAL24: Показать кнопку Карт',

        # PAYMENTS - OTHER
        'MULENPAY_ENABLED': 'Включить MulenPay',
        'MULENPAY_SHOP_ID': 'MulenPay: Shop ID',
        'MULENPAY_API_KEY': 'MulenPay: API Key',
        'MULENPAY_SECRET_KEY': 'MulenPay: Secret Key',
        'WATA_ENABLED': 'Включить Wata',
        'WATA_ACCESS_TOKEN': 'Wata: Токен доступа',
        'WATA_TERMINAL_PUBLIC_ID': 'Wata: ID терминала',
        'CLOUDPAYMENTS_ENABLED': 'Включить CloudPayments',
        'CLOUDPAYMENTS_PUBLIC_ID': 'CloudPayments: Public ID',
        'CLOUDPAYMENTS_API_SECRET': 'CloudPayments: API Secret',
        'CLOUDPAYMENTS_SKIN': 'CloudPayments: Дизайн виджета',
        'HELEKET_ENABLED': 'Включить Heleket Crypto',
        'HELEKET_MERCHANT_ID': 'Heleket: Merchant ID',
        'HELEKET_API_KEY': 'Heleket: API Key',
        'HELEKET_DEFAULT_CURRENCY': 'Heleket: Валюта (USDT)',
        'PLATEGA_ENABLED': 'Включить Platega',
        'PLATEGA_MERCHANT_ID': 'Platega: Merchant ID',
        'PLATEGA_SECRET': 'Platega: Секрет (Secret)',
        'TRIBUTE_ENABLED': 'Включить Tribute (карты)',
        'TRIBUTE_API_KEY': 'Tribute: API Key',
        'TRIBUTE_DONATE_LINK': 'Tribute: Ссылка на донат',
        
        # WEBHOOK NOTIFICATIONS
        'WEBHOOK_NOTIFY_USER_ENABLED': 'Включить уведомления по вебхукам',
        'WEBHOOK_NOTIFY_SUB_STATUS': 'Увед: Изменение статуса',
        'WEBHOOK_NOTIFY_SUB_EXPIRED': 'Увед: Подписка истекла',
        'WEBHOOK_NOTIFY_SUB_EXPIRING': 'Увед: Подписка истекает',
        'WEBHOOK_NOTIFY_SUB_LIMITED': 'Увед: Лимит трафика исчерпан',
        'WEBHOOK_NOTIFY_TRAFFIC_RESET': 'Увед: Сброс трафика',
        'WEBHOOK_NOTIFY_SUB_DELETED': 'Увед: Удаление подписки',
        'WEBHOOK_NOTIFY_SUB_REVOKED': 'Увед: Отзыв подписки (Revoke)',
        'WEBHOOK_NOTIFY_FIRST_CONNECTED': 'Увед: Первое подключение к VPN',
        'WEBHOOK_NOTIFY_NOT_CONNECTED': 'Увед: Напоминание о подключении',
        'WEBHOOK_NOTIFY_BANDWIDTH_THRESHOLD': 'Увед: Порог трафика (%)',
        'WEBHOOK_NOTIFY_DEVICES': 'Увед: Изменение лимита устройств',

        # NALOGO
        'NALOGO_ENABLED': 'Включить чеки NaloGO (Самозанятые)',
        'NALOGO_INN': 'NaloGO: ИНН самозанятого',
        'NALOGO_PASSWORD': 'NaloGO: Пароль (ЛК Мой Налог)',
        'NALOGO_DEVICE_ID': 'NaloGO: ID устройства',
        'NALOGO_STORAGE_PATH': 'NaloGO: Путь к токенам (.json)',
        'NALOGO_QUEUE_CHECK_INTERVAL': 'Интервал обработки очереди (сек)',
        'NALOGO_QUEUE_RECEIPT_DELAY': 'Задержка отправки чеков (сек)',
        'NALOGO_QUEUE_MAX_ATTEMPTS': 'Макс. попыток отправки чека',
    }

    CATEGORY_DESCRIPTIONS: dict[str, str] = {
        'CORE': 'Базовые параметры работы бота и обязательные ссылки.',
        'SUPPORT': 'Контакты поддержки, SLA и режимы обработки обращений.',
        'LOCALIZATION': 'Доступные языки, локализация интерфейса и выбор языка.',
        'CHANNEL': 'Настройки обязательной подписки на канал или группу.',
        'TIMEZONE': 'Часовой пояс панели и отображение времени.',
        'PAYMENT': 'Общие тексты платежей, описания чеков и шаблоны.',
        'PAYMENT_VERIFICATION': 'Автоматическая проверка пополнений и интервал выполнения.',
        'YOOKASSA': 'Интеграция с YooKassa: идентификаторы магазина и вебхуки.',
        'CRYPTOBOT': 'CryptoBot и криптоплатежи через Telegram.',
        'HELEKET': 'Heleket: криптоплатежи, ключи мерчанта и вебхуки.',
        'CLOUDPAYMENTS': 'CloudPayments: оплата банковскими картами, Public ID, API Secret и вебхуки.',
        'FREEKASSA': 'Freekassa: ID магазина, API ключ, секретные слова и вебхуки.',
        'KASSA_AI': 'KassaAI: отдельная платёжка api.fk.life с СБП, картами и SberPay.',
        'PLATEGA': '{platega_name}: merchant ID, секрет, ссылки возврата и методы оплаты.',
        'MULENPAY': 'Платежи {mulenpay_name} и параметры магазина.',
        'PAL24': 'PAL24 / PayPalych подключения и лимиты.',
        'TRIBUTE': 'Tribute и донат-сервисы.',
        'TELEGRAM': 'Telegram Stars и их стоимость.',
        'WATA': 'Wata: токен доступа, тип платежа и пределы сумм.',
        'EXTERNAL_ADMIN': 'Токен внешней админки для проверки запросов.',
        'SUBSCRIPTIONS_CORE': 'Лимиты устройств, трафика и базовые цены подписок.',
        'SIMPLE_SUBSCRIPTION': 'Параметры упрощённой покупки: период, трафик, устройства и сквады.',
        'PERIODS': 'Доступные периоды подписок и продлений.',
        'SUBSCRIPTION_PRICES': 'Стоимость подписок по периодам в копейках.',
        'TRAFFIC': 'Лимиты трафика и стратегии сброса.',
        'TRAFFIC_PACKAGES': 'Цены пакетов трафика и конфигурация предложений.',
        'TRIAL': 'Длительность и ограничения пробного периода.',
        'REFERRAL': 'Бонусы и пороги реферальной программы.',
        'AUTOPAY': 'Настройки автопродления и минимальный баланс.',
        'NOTIFICATIONS': 'Пользовательские уведомления и кэширование сообщений.',
        'ADMIN_NOTIFICATIONS': 'Оповещения админам о событиях и тикетах.',
        'ADMIN_REPORTS': 'Автоматические отчеты для команды.',
        'INTERFACE': 'Глобальные параметры интерфейса и брендирования.',
        'INTERFACE_BRANDING': 'Логотип и фирменный стиль.',
        'INTERFACE_SUBSCRIPTION': 'Отображение ссылок и кнопок подписок.',
        'CONNECT_BUTTON': 'Поведение кнопки «Подключиться» и miniapp.',
        'MINIAPP': 'Mini App и кастомные ссылки.',
        'HAPP': 'Интеграция Happ и связанные ссылки.',
        'SKIP': 'Настройки быстрого старта и гайд по подключению.',
        'ADDITIONAL': 'Конфигурация deep links и кеша.',
        'DATABASE': 'Режим работы базы данных и пути до файлов.',
        'POSTGRES': 'Параметры подключения к PostgreSQL.',
        'SQLITE': 'Файл SQLite и резервные параметры.',
        'REDIS': 'Подключение к Redis для кэша.',
        'REMNAWAVE': 'Параметры авторизации и интеграция с RemnaWave API.',
        'SERVER_STATUS': 'Отображение статуса серверов и external URL.',
        'MONITORING': 'Интервалы мониторинга и хранение логов.',
        'MAINTENANCE': 'Режим обслуживания, сообщения и интервалы.',
        'BACKUP': 'Резервное копирование и расписание.',
        'VERSION': 'Отслеживание обновлений репозитория.',
        'WEB_API': 'Web API, токены и права доступа.',
        'WEBHOOK': 'Пути и секреты вебхуков.',
        'WEBHOOK_NOTIFICATIONS': 'Управление уведомлениями, которые получают пользователи при событиях RemnaWave (отключение/активация подписки, устройства, трафик и т.д.) в реальном времени.',
        'LOG': 'Уровни логирования и ротация логов.',
        'DEBUG': 'Отладочные функции и безопасный режим.',
        'MODERATION': 'Настройки фильтров отображаемых имен и защиты от фишинга.',
        'BAN_NOTIFICATIONS': 'Тексты уведомлений о блокировках, которые отправляются пользователям.',
        'SUPPORT_AI': 'Настройки AI-ассистента первой линии: Telegram Forum группа, провайдеры, ключи и системный промпт.',
        'GIFTS': 'Настройка функционала подарков: включение системы, оформление кнопки в меню и шаблоны приглашений.',
        'NALOGO': 'Интеграция с сервисом NaloGO для автоматического формирования чеков самозанятых при оплате.',
        'CABINET': 'Настройки Личного Кабинета: URL, авторизация через OAuth, сессии (JWT) и подтверждение почты.',
        'OAUTH': 'Настройки интеграции с внешними провайдерами авторизации (Google, Yandex, Discord, VK).',
    }

    @staticmethod
    def _format_dynamic_copy(category_key: str | None, value: str) -> str:
        if not value:
            return value
        if category_key == 'MULENPAY':
            return value.format(mulenpay_name=settings.get_mulenpay_display_name())
        if category_key == 'PLATEGA':
            return value.format(platega_name=settings.get_platega_display_name())
        return value

    CATEGORY_KEY_OVERRIDES: dict[str, str] = {
        'DATABASE_URL': 'DATABASE',
        'DATABASE_MODE': 'DATABASE',
        'LOCALES_PATH': 'LOCALIZATION',
        'CHANNEL_IS_REQUIRED_SUB': 'CHANNEL',
        'BOT_USERNAME': 'CORE',
        'DEFAULT_LANGUAGE': 'LOCALIZATION',
        'AVAILABLE_LANGUAGES': 'LOCALIZATION',
        'LANGUAGE_SELECTION_ENABLED': 'LOCALIZATION',
        'DEFAULT_DEVICE_LIMIT': 'SUBSCRIPTIONS_CORE',
        'FIXED_TRAFFIC_LIMIT_GB': 'SUBSCRIPTIONS_CORE',
        'BUY_SUBSCRIPTION_BUTTON_TEXT': 'SUBSCRIPTIONS_CORE',
        'BUY_SUBSCRIPTION_BUTTON_STYLE': 'SUBSCRIPTIONS_CORE',
        'BUY_SUBSCRIPTION_BUTTON_EMOJI': 'SUBSCRIPTIONS_CORE',
        'SUBSCRIPTION_BUTTON_TEXT': 'SUBSCRIPTIONS_CORE',
        'BUY_TRAFFIC_BUTTON_VISIBLE': 'SUBSCRIPTIONS_CORE',
        'DEFAULT_TRAFFIC_LIMIT_GB': 'SUBSCRIPTIONS_CORE',
        'MAX_DEVICES_LIMIT': 'SUBSCRIPTIONS_CORE',
        'PRICE_PER_DEVICE': 'SUBSCRIPTIONS_CORE',
        'DEVICES_SELECTION_ENABLED': 'SUBSCRIPTIONS_CORE',
        'DEVICES_SELECTION_DISABLED_AMOUNT': 'SUBSCRIPTIONS_CORE',
        'BASE_SUBSCRIPTION_PRICE': 'SUBSCRIPTIONS_CORE',
        'SALES_MODE': 'SUBSCRIPTIONS_CORE',
        'DEFAULT_TRAFFIC_RESET_STRATEGY': 'TRAFFIC',
        'RESET_TRAFFIC_ON_PAYMENT': 'TRAFFIC',
        'RESET_TRAFFIC_ON_TARIFF_SWITCH': 'TRAFFIC',
        'TRAFFIC_SELECTION_MODE': 'TRAFFIC',
        'FIXED_TRAFFIC_LIMIT_GB': 'TRAFFIC',
        'AVAILABLE_SUBSCRIPTION_PERIODS': 'PERIODS',
        'AVAILABLE_RENEWAL_PERIODS': 'PERIODS',
        'PRICE_14_DAYS': 'SUBSCRIPTION_PRICES',
        'PRICE_30_DAYS': 'SUBSCRIPTION_PRICES',
        'PRICE_60_DAYS': 'SUBSCRIPTION_PRICES',
        'PRICE_90_DAYS': 'SUBSCRIPTION_PRICES',
        'PRICE_180_DAYS': 'SUBSCRIPTION_PRICES',
        'PRICE_360_DAYS': 'SUBSCRIPTION_PRICES',
        'REFERRAL_BUTTON_TEXT': 'REFERRAL',
        'REFERRAL_BUTTON_STYLE': 'REFERRAL',
        'REFERRAL_BUTTON_EMOJI': 'REFERRAL',
        'PAID_SUBSCRIPTION_USER_TAG': 'SUBSCRIPTION_PRICES',
        'TRAFFIC_PACKAGES_CONFIG': 'TRAFFIC_PACKAGES',
        'BASE_PROMO_GROUP_PERIOD_DISCOUNTS_ENABLED': 'SUBSCRIPTIONS_CORE',
        'BASE_PROMO_GROUP_PERIOD_DISCOUNTS': 'SUBSCRIPTIONS_CORE',
        'DEFAULT_AUTOPAY_ENABLED': 'AUTOPAY',
        'DEFAULT_AUTOPAY_DAYS_BEFORE': 'AUTOPAY',
        'MIN_BALANCE_FOR_AUTOPAY_KOPEKS': 'AUTOPAY',
        'TRIAL_WARNING_HOURS': 'TRIAL',
        'TRIAL_USER_TAG': 'TRIAL',
        'SUPPORT_USERNAME': 'SUPPORT',
        'SUPPORT_MENU_ENABLED': 'SUPPORT',
        'SUPPORT_SYSTEM_MODE': 'SUPPORT',
        'SUPPORT_TICKET_SLA_ENABLED': 'SUPPORT',
        'SUPPORT_TICKET_SLA_MINUTES': 'SUPPORT',
        'SUPPORT_TICKET_SLA_CHECK_INTERVAL_SECONDS': 'SUPPORT',
        'SUPPORT_TICKET_SLA_REMINDER_COOLDOWN_MINUTES': 'SUPPORT',
        'SUPPORT_AI_FORUM_ID': 'SUPPORT_AI',
        'SUPPORT_AI_ENABLED': 'SUPPORT_AI',
        'ADMIN_NOTIFICATIONS_ENABLED': 'ADMIN_NOTIFICATIONS',
        'ADMIN_NOTIFICATIONS_CHAT_ID': 'ADMIN_NOTIFICATIONS',
        'ADMIN_NOTIFICATIONS_TOPIC_ID': 'ADMIN_NOTIFICATIONS',
        'ADMIN_NOTIFICATIONS_TICKET_TOPIC_ID': 'ADMIN_NOTIFICATIONS',
        'ADMIN_REPORTS_ENABLED': 'ADMIN_REPORTS',
        'ADMIN_REPORTS_CHAT_ID': 'ADMIN_REPORTS',
        'ADMIN_REPORTS_TOPIC_ID': 'ADMIN_REPORTS',
        'ADMIN_REPORTS_SEND_TIME': 'ADMIN_REPORTS',
        'PAYMENT_SERVICE_NAME': 'PAYMENT',
        'PAYMENT_BALANCE_DESCRIPTION': 'PAYMENT',
        'PAYMENT_SUBSCRIPTION_DESCRIPTION': 'PAYMENT',
        'PAYMENT_BALANCE_TEMPLATE': 'PAYMENT',
        'PAYMENT_SUBSCRIPTION_TEMPLATE': 'PAYMENT',
        'AUTO_PURCHASE_AFTER_TOPUP_ENABLED': 'PAYMENT',
        'SIMPLE_SUBSCRIPTION_ENABLED': 'SIMPLE_SUBSCRIPTION',
        'SIMPLE_SUBSCRIPTION_PERIOD_DAYS': 'SIMPLE_SUBSCRIPTION',
        'SIMPLE_SUBSCRIPTION_DEVICE_LIMIT': 'SIMPLE_SUBSCRIPTION',
        'SIMPLE_SUBSCRIPTION_TRAFFIC_GB': 'SIMPLE_SUBSCRIPTION',
        'SIMPLE_SUBSCRIPTION_SQUAD_UUID': 'SIMPLE_SUBSCRIPTION',
        'DISABLE_TOPUP_BUTTONS': 'PAYMENT',
        'SUPPORT_TOPUP_ENABLED': 'PAYMENT',
        'ENABLE_NOTIFICATIONS': 'NOTIFICATIONS',
        'NOTIFICATION_RETRY_ATTEMPTS': 'NOTIFICATIONS',
        'NOTIFICATION_CACHE_HOURS': 'NOTIFICATIONS',
        'MONITORING_LOGS_RETENTION_DAYS': 'MONITORING',
        'MONITORING_INTERVAL': 'MONITORING',
        'TRAFFIC_MONITORING_ENABLED': 'MONITORING',
        'TRAFFIC_MONITORING_INTERVAL_HOURS': 'MONITORING',
        'TRAFFIC_MONITORED_NODES': 'MONITORING',
        'TRAFFIC_SNAPSHOT_TTL_HOURS': 'MONITORING',
        'TRAFFIC_FAST_CHECK_ENABLED': 'MONITORING',
        'TRAFFIC_FAST_CHECK_INTERVAL_MINUTES': 'MONITORING',
        'TRAFFIC_FAST_CHECK_THRESHOLD_GB': 'MONITORING',
        'TRAFFIC_DAILY_CHECK_ENABLED': 'MONITORING',
        'TRAFFIC_DAILY_CHECK_TIME': 'MONITORING',
        'TRAFFIC_DAILY_THRESHOLD_GB': 'MONITORING',
        'TRAFFIC_IGNORED_NODES': 'MONITORING',
        'TRAFFIC_EXCLUDED_USER_UUIDS': 'MONITORING',
        'TRAFFIC_NOTIFICATION_COOLDOWN_MINUTES': 'MONITORING',
        'SUSPICIOUS_NOTIFICATIONS_TOPIC_ID': 'MONITORING',
        'TRAFFIC_CHECK_BATCH_SIZE': 'MONITORING',
        'TRAFFIC_CHECK_CONCURRENCY': 'MONITORING',
        'ENABLE_LOGO_MODE': 'INTERFACE_BRANDING',
        'LOGO_FILE': 'INTERFACE_BRANDING',
        'HIDE_SUBSCRIPTION_LINK': 'INTERFACE_SUBSCRIPTION',
        'MAIN_MENU_MODE': 'INTERFACE',
        'CABINET_BUTTON_STYLE': 'INTERFACE',
        'CONNECT_BUTTON_MODE': 'CONNECT_BUTTON',
        'MINIAPP_CUSTOM_URL': 'CONNECT_BUTTON',
        'ENABLE_DEEP_LINKS': 'ADDITIONAL',
        'APP_CONFIG_CACHE_TTL': 'ADDITIONAL',
        'INACTIVE_USER_DELETE_MONTHS': 'MAINTENANCE',
        'MAINTENANCE_MESSAGE': 'MAINTENANCE',
        'MAINTENANCE_CHECK_INTERVAL': 'MAINTENANCE',
        'MAINTENANCE_AUTO_ENABLE': 'MAINTENANCE',
        'MAINTENANCE_RETRY_ATTEMPTS': 'MAINTENANCE',
        'WEBHOOK_URL': 'WEBHOOK',
        'WEBHOOK_SECRET': 'WEBHOOK',
        'VERSION_CHECK_ENABLED': 'VERSION',
        'VERSION_CHECK_REPO': 'VERSION',
        'VERSION_CHECK_INTERVAL_HOURS': 'VERSION',
        'TELEGRAM_STARS_RATE_RUB': 'TELEGRAM',
        'REMNAWAVE_USER_DESCRIPTION_TEMPLATE': 'REMNAWAVE',
        'REMNAWAVE_USER_USERNAME_TEMPLATE': 'REMNAWAVE',
        'REMNAWAVE_AUTO_SYNC_ENABLED': 'REMNAWAVE',
        'REMNAWAVE_AUTO_SYNC_TIMES': 'REMNAWAVE',
        'CABINET_REMNA_SUB_CONFIG': 'MINIAPP',
        'USE_PREMIUM_EMOJIS': 'INTERFACE_BRANDING',
        'PREMIUM_EMOJIS_DATA': 'INTERFACE_BRANDING',
        'GIFTS_ENABLED': 'GIFTS',
        'GIFTS_BUTTON_VISIBLE': 'GIFTS',
        'GIFTS_BUTTON_TEXT': 'GIFTS',
        'GIFTS_BUTTON_STYLE': 'GIFTS',
        'GIFTS_BUTTON_EMOJI': 'GIFTS',
        'GIFTS_SHARE_MESSAGE_TEMPLATE': 'GIFTS',
    }

    CATEGORY_PREFIX_OVERRIDES: dict[str, str] = {
        'SUPPORT_': 'SUPPORT',
        'ADMIN_NOTIFICATIONS': 'ADMIN_NOTIFICATIONS',
        'ADMIN_REPORTS': 'ADMIN_REPORTS',
        'CHANNEL_': 'CHANNEL',
        'POSTGRES_': 'POSTGRES',
        'SQLITE_': 'SQLITE',
        'REDIS_': 'REDIS',
        'REMNAWAVE': 'REMNAWAVE',
        'TRIAL_': 'TRIAL',
        'TRAFFIC_PACKAGES': 'TRAFFIC_PACKAGES',
        'PRICE_TRAFFIC': 'TRAFFIC_PACKAGES',
        'TRAFFIC_': 'TRAFFIC',
        'REFERRAL_': 'REFERRAL',
        'AUTOPAY_': 'AUTOPAY',
        'TELEGRAM_STARS': 'TELEGRAM',
        'TRIBUTE_': 'TRIBUTE',
        'YOOKASSA_': 'YOOKASSA',
        'CRYPTOBOT_': 'CRYPTOBOT',
        'HELEKET_': 'HELEKET',
        'CLOUDPAYMENTS_': 'CLOUDPAYMENTS',
        'FREEKASSA_': 'FREEKASSA',
        'KASSA_AI_': 'KASSA_AI',
        'PLATEGA_': 'PLATEGA',
        'MULENPAY_': 'MULENPAY',
        'PAL24_': 'PAL24',
        'PAYMENT_': 'PAYMENT',
        'PAYMENT_VERIFICATION_': 'PAYMENT_VERIFICATION',
        'WATA_': 'WATA',
        'EXTERNAL_ADMIN_': 'EXTERNAL_ADMIN',
        'SIMPLE_SUBSCRIPTION_': 'SIMPLE_SUBSCRIPTION',
        'CONNECT_BUTTON_HAPP': 'HAPP',
        'HAPP_': 'HAPP',
        'SKIP_': 'SKIP',
        'MINIAPP_': 'MINIAPP',
        'MONITORING_': 'MONITORING',
        'NOTIFICATION_': 'NOTIFICATIONS',
        'SERVER_STATUS': 'SERVER_STATUS',
        'MAINTENANCE_': 'MAINTENANCE',
        'VERSION_CHECK': 'VERSION',
        'BACKUP_': 'BACKUP',
        'WEBHOOK_NOTIFY_': 'WEBHOOK_NOTIFICATIONS',
        'WEBHOOK_': 'WEBHOOK',
        'LOG_': 'LOG',
        'WEB_API_': 'WEB_API',
        'DEBUG': 'DEBUG',
        'DISPLAY_NAME_': 'MODERATION',
        'BAN_MSG_': 'BAN_NOTIFICATIONS',
        'BLACKLIST_': 'MODERATION',
        'CABINET_': 'CABINET',
        'OAUTH_': 'OAUTH',
        'SMTP_': 'CABINET',
        'SUPPORT_AI_': 'SUPPORT_AI',
        'GIFTS_': 'GIFTS',
        'NALOGO_': 'NALOGO',
    }

    CHOICES: dict[str, list[ChoiceOption]] = {
        'DATABASE_MODE': [
            ChoiceOption('auto', '🤖 Авто'),
            ChoiceOption('postgresql', '🐘 PostgreSQL'),
            ChoiceOption('sqlite', '💾 SQLite'),
        ],
        'REMNAWAVE_AUTH_TYPE': [
            ChoiceOption('api_key', '🔑 API Key'),
            ChoiceOption('basic_auth', '🧾 Basic Auth'),
        ],
        'REMNAWAVE_USER_DELETE_MODE': [
            ChoiceOption('delete', '🗑 Удалять'),
            ChoiceOption('disable', '🚫 Деактивировать'),
        ],
        'TRAFFIC_SELECTION_MODE': [
            ChoiceOption('selectable', '📦 Выбор пакетов'),
            ChoiceOption('fixed', '📏 Фиксированный лимит'),
            ChoiceOption('fixed_with_topup', '📏 Фикс. лимит + докупка'),
        ],
        'DEFAULT_TRAFFIC_RESET_STRATEGY': [
            ChoiceOption('NO_RESET', '♾️ Без сброса'),
            ChoiceOption('DAY', '📅 Ежедневно'),
            ChoiceOption('WEEK', '🗓 Еженедельно'),
            ChoiceOption('MONTH', '📆 Ежемесячно'),
        ],
        'SUPPORT_SYSTEM_MODE': [
            ChoiceOption('tickets', '🎫 Только тикеты'),
            ChoiceOption('contact', '💬 Только контакт'),
            ChoiceOption('both', '🔁 Оба варианта'),
            ChoiceOption('ai_tiket', '🤖 DonMatteo-AI-Tiket'),
        ],

        'CONNECT_BUTTON_MODE': [
            ChoiceOption('guide', '📘 Гайд'),
            ChoiceOption('miniapp_subscription', '🧾 Mini App подписка'),
            ChoiceOption('miniapp_custom', '🧩 Mini App (ссылка)'),
            ChoiceOption('link', '🔗 Прямая ссылка'),
            ChoiceOption('happ_cryptolink', '🪙 Happ CryptoLink'),
        ],
        'MAIN_MENU_MODE': [
            ChoiceOption('default', '📋 Полное меню'),
            ChoiceOption('cabinet', '🏠 Cabinet (МиниАпп)'),
        ],
        'CABINET_BUTTON_STYLE': [
            ChoiceOption('', '🎨 По секциям (авто)'),
            ChoiceOption('primary', '🔵 Синий'),
            ChoiceOption('success', '🟢 Зелёный'),
            ChoiceOption('danger', '🔴 Красный'),
        ],
        'SALES_MODE': [
            ChoiceOption('classic', '📋 Классический (периоды из .env)'),
            ChoiceOption('tariffs', '📦 Тарифы (из кабинета)'),
        ],
        'SERVER_STATUS_MODE': [
            ChoiceOption('disabled', '🚫 Отключено'),
            ChoiceOption('external_link', '🌐 Внешняя ссылка'),
            ChoiceOption('external_link_miniapp', '🧭 Mini App ссылка'),
            ChoiceOption('xray', '📊 XRay Checker'),
        ],
        'YOOKASSA_PAYMENT_MODE': [
            ChoiceOption('full_payment', '💳 Полная оплата'),
            ChoiceOption('partial_payment', '🪙 Частичная оплата'),
            ChoiceOption('advance', '💼 Аванс'),
            ChoiceOption('full_prepayment', '📦 Полная предоплата'),
            ChoiceOption('partial_prepayment', '📦 Частичная предоплата'),
            ChoiceOption('credit', '💰 Кредит'),
            ChoiceOption('credit_payment', '💸 Погашение кредита'),
        ],
        'YOOKASSA_PAYMENT_SUBJECT': [
            ChoiceOption('commodity', '📦 Товар'),
            ChoiceOption('excise', '🥃 Подакцизный товар'),
            ChoiceOption('job', '🛠 Работа'),
            ChoiceOption('service', '🧾 Услуга'),
            ChoiceOption('gambling_bet', '🎲 Ставка'),
            ChoiceOption('gambling_prize', '🏆 Выигрыш'),
            ChoiceOption('lottery', '🎫 Лотерея'),
            ChoiceOption('lottery_prize', '🎁 Приз лотереи'),
            ChoiceOption('intellectual_activity', '🧠 Интеллектуальная деятельность'),
            ChoiceOption('payment', '💱 Платеж'),
            ChoiceOption('agent_commission', '🤝 Комиссия агента'),
            ChoiceOption('composite', '🧩 Композитный'),
            ChoiceOption('another', '📄 Другое'),
        ],
        'YOOKASSA_VAT_CODE': [
            ChoiceOption(1, '1 — НДС не облагается'),
            ChoiceOption(2, '2 — НДС 0%'),
            ChoiceOption(3, '3 — НДС 10%'),
            ChoiceOption(4, '4 — НДС 20%'),
            ChoiceOption(5, '5 — НДС 10/110'),
            ChoiceOption(6, '6 — НДС 20/120'),
            ChoiceOption(7, '7 — НДС 5%'),
            ChoiceOption(8, '8 — НДС 7%'),
            ChoiceOption(9, '9 — НДС 5/105'),
            ChoiceOption(10, '10 — НДС 7/107'),
            ChoiceOption(11, '11 — НДС 22%'),
            ChoiceOption(12, '12 — НДС 22/122'),
        ],
        'MULENPAY_LANGUAGE': [
            ChoiceOption('ru', '🇷🇺 Русский'),
            ChoiceOption('en', '🇬🇧 Английский'),
        ],
        'LOG_LEVEL': [
            ChoiceOption('DEBUG', '🐞 Debug'),
            ChoiceOption('INFO', 'ℹ️ Info'),
            ChoiceOption('WARNING', '⚠️ Warning'),
            ChoiceOption('ERROR', '❌ Error'),
            ChoiceOption('CRITICAL', '🔥 Critical'),
        ],
        'TRIAL_DISABLED_FOR': [
            ChoiceOption('none', '✅ Включён для всех'),
            ChoiceOption('email', '📧 Отключён для Email'),
            ChoiceOption('telegram', '📱 Отключён для Telegram'),
            ChoiceOption('all', '🚫 Отключён для всех'),
        ],
        'GIFTS_BUTTON_STYLE': [
            ChoiceOption('primary', '🔵 Синий'),
            ChoiceOption('success', '🟢 Зелёный'),
            ChoiceOption('danger', '🔴 Красный'),
            ChoiceOption('default', '⚪ Серый'),
        ],
        'REFERRAL_BUTTON_STYLE': [
            ChoiceOption('primary', '🔵 Синий'),
            ChoiceOption('success', '🟢 Зелёный'),
            ChoiceOption('danger', '🔴 Красный'),
            ChoiceOption('default', '⚪ Серый'),
        ],
        'BUY_SUBSCRIPTION_BUTTON_STYLE': [
            ChoiceOption('primary', '🔵 Синий'),
            ChoiceOption('success', '🟢 Зелёный'),
            ChoiceOption('danger', '🔴 Красный'),
            ChoiceOption('default', '⚪ Серый'),
        ],
    }

    SETTING_HINTS: dict[str, dict[str, str]] = {
        'SALES_MODE': {
            'description': 'Определяет, как пользователи будут выбирать услуги. «Классический» — гибкий конструктор (периоды, трафик, устройства отдельно). «Тарифы» — готовые пакеты с фиксированными параметрами из вашего Личного Кабинета.',
            'format': 'Выберите один из двух стилей продаж.',
            'example': 'tariffs — для простоты и скорости покупки.',
            'warning': 'Смена режима полностью меняет интерфейс покупки для всех пользователей.',
        },
        'AVAILABLE_SUBSCRIPTION_PERIODS': {
            'description': 'Дни, которые бот предложит пользователю при покупке. Важно: для каждого указанного здесь числа дней должна быть задана соответствующая цена в блоке «Стоимость».',
            'format': 'Числа через запятую (напр. 30, 90, 360).',
            'example': '30, 90, 180, 360',
            'warning': 'Если вы добавите новый период, обязательно пропишите для него цену (PRICE_XX_DAYS), иначе кнопка в боте не сработает.',
        },
        'AVAILABLE_RENEWAL_PERIODS': {
            'description': 'Список дней для быстрого продления. Обычно совпадает с основным списком, но здесь можно оставить только самые выгодные варианты.',
            'format': 'Дни через запятую.',
            'example': '30, 90',
            'warning': 'Проверьте наличие цен для каждого указанного периода.',
        },
        'BUY_SUBSCRIPTION_BUTTON_TEXT': {
            'description': 'Текст, который будет написан на кнопке покупки подписки в главном меню.',
            'format': 'Текстовая строка.',
            'example': '💎 Купить подписку',
        },
        'BUY_SUBSCRIPTION_BUTTON_STYLE': {
            'description': 'Цветовое оформление кнопки покупки в главном меню.',
            'format': 'Выберите один из четырех цветов.',
            'example': 'Зелёный (рекомендуется для CTA)',
        },
        'BUY_SUBSCRIPTION_BUTTON_EMOJI': {
            'description': (
                'Позволяет использовать красивый анимированный премиум-эмодзи для кнопки покупки. '
                'Для этого отправьте нужный эмодзи боту @EmojiIdBot и вставьте полученный ID сюда.'
            ),
            'format': 'ID премиум-эмодзи.',
            'warning': 'Будет работать только в официальных приложениях Telegram.',
        },
        'SUBSCRIPTION_BUTTON_TEXT': {
            'description': 'Текст для общего раздела подписки (в нижней Reply-клавиатуре и в меню личного кабинета).',
            'format': 'Текстовая строка.',
            'example': '📱 Моя подписка',
        },
        'PRICE_14_DAYS': {
            'description': 'Стоимость подписки на 14 дней. Часто используется как «Пробная платная версия» для новых клиентов.',
            'format': 'Цена в копейках (100 руб = 10000).',
            'example': '50000 (500 руб)',
        },
        'PRICE_30_DAYS': {
            'description': 'Основная цена за 30 дней (1 месяц) использования VPN. Самая важная настройка доходности.',
            'format': 'Цена в копейках.',
            'example': '99000 (990 руб)',
        },
        'PRICE_60_DAYS': {
            'description': 'Стоимость подписки на 2 месяца. Рекомендуется ставить цену чуть ниже, чем за два отдельных месяца.',
            'format': 'Цена в копейках.',
        },
        'PRICE_90_DAYS': {
            'description': 'Стоимость квартальной подписки (3 месяца). Психологически важный рубеж для удержания клиентов.',
            'format': 'Цена в копейках.',
        },
        'PRICE_180_DAYS': {
            'description': 'Стоимость подписки на полгода (6 месяцев). Обычно на этот период ставят значительную скидку (15-20%).',
            'format': 'Цена в копейках.',
        },
        'PRICE_360_DAYS': {
            'description': 'Годовая подписка. Позволяет получить максимальную сумму с клиента сразу. Рекомендуется самая выгодная цена.',
            'format': 'Цена в копейках.',
        },
        'PRICE_PER_DEVICE': {
            'description': 'Стоимость добавления одного дополнительного устройства к подписке. Если пользователю мало лимита по умолчанию, он может докупить его.',
            'format': 'Цена за 1 устройство в копейках.',
            'example': '5000 (50 руб)',
        },
        'TRAFFIC_SELECTION_MODE': {
            'description': 'Как пользователь получает трафик: «Выбор пакетов» (сам выбирает ГБ при покупке и может докупать) или «Фикс. лимит» (получает строго по тарифу без выбора).',
            'format': 'Выберите режим распределения ГБ.',
            'example': 'selectable — дает пользователю гибкость.',
        },
        'PRICE_TRAFFIC_5GB': { 
            'description': 'Цена за пакет 5 Гигабайт трафика. Если вы не хотите продавать такой объем, установите 0.', 
            'format': 'Копейки (10000 = 100 руб).',
            'example': '5000 (50 руб)',
        },
        'PRICE_TRAFFIC_10GB': { 
            'description': 'Цена за пакет 10 Гигабайт. Средний объем для нечастого использования.', 
            'format': 'Копейки.',
            'example': '9000 (90 руб)',
        },
        'PRICE_TRAFFIC_25GB': { 
            'description': 'Цена за пакет 25 Гигабайт.', 
            'format': 'Копейки.',
            'example': '20000 (200 руб)',
        },
        'PRICE_TRAFFIC_50GB': { 
            'description': 'Цена за пакет 50 Гигабайт. Популярный выбор для активных пользователей.', 
            'format': 'Копейки.',
            'example': '35000 (350 руб)',
        },
        'PRICE_TRAFFIC_100GB': { 
            'description': 'Цена за пакет 100 Гигабайт.', 
            'format': 'Копейки.',
        },
        'PRICE_TRAFFIC_250GB': { 
            'description': 'Цена за пакет 250 Гигабайт. Подойдет для просмотра видео в высоком качестве.', 
            'format': 'Копейки.',
        },
        'PRICE_TRAFFIC_500GB': { 
            'description': 'Цена за пакет 500 Гигабайт трафика.', 
            'format': 'Копейки.',
        },
        'PRICE_TRAFFIC_1000GB': { 
            'description': 'Цена за пакет 1000 Гигабайт (1 ТБ).', 
            'format': 'Копейки.',
        },
        'PRICE_TRAFFIC_UNLIMITED': {
            'description': 'Стоимость полной отмены лимитов трафика. Пользователь получит безлимитный доступ навсегда на оплаченный период подписки.',
            'format': 'Цена в копейках.',
            'example': '150000 (1500 руб)',
            'warning': 'Безлимит — премиальная опция, рекомендуется ставить цену выше среднего пакета.',
        },
        'YOOKASSA_ENABLED': {
            'description': 'Включает прием платежей через YooKassa. Это основной шлюз для работы с российскими картами и СБП.',
            'format': 'Включите после настройки Shop ID.',
            'warning': 'Для работы обязателен договор с YooKassa и заполненные API ключи.',
            'dependencies': 'YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY',
        },
        'CRYPTOBOT_ENABLED': {
            'description': 'Разрешает оплату криптовалютой (USDT, TON, BTC) через популярного бота @CryptoBot.',
            'format': 'Включите для работы с крипто-кошельками.',
            'warning': 'Убедитесь, что токен API версии v1 корректен.',
            'dependencies': 'CRYPTOBOT_API_TOKEN, CRYPTOBOT_WEBHOOK_SECRET',
        },
        'PAYMENT_VERIFICATION_AUTO_CHECK_ENABLED': {
            'description': (
                'Запускает фоновую проверку ожидающих пополнений и повторно обращается '
                'к платёжным провайдерам без участия администратора.'
            ),
            'format': 'Булево значение.',
            'example': 'Включено, чтобы автоматически перепроверять зависшие платежи.',
            'warning': 'Требует активных интеграций YooKassa, {mulenpay_name}, PayPalych, WATA или CryptoBot.',
        },
        'PAYMENT_VERIFICATION_AUTO_CHECK_INTERVAL_MINUTES': {
            'description': ('Интервал между автоматическими проверками ожидающих пополнений в минутах.'),
            'format': 'Целое число не меньше 1.',
            'example': '10',
            'warning': 'Слишком малый интервал может привести к частым обращениям к платёжным API.',
            'dependencies': 'PAYMENT_VERIFICATION_AUTO_CHECK_ENABLED',
        },
        'BASE_PROMO_GROUP_PERIOD_DISCOUNTS_ENABLED': {
            'description': ('Включает применение базовых скидок на периоды подписок в групповых промо.'),
            'format': 'Булево значение.',
            'example': 'true',
            'warning': 'Скидки применяются только если указаны корректные пары периодов и процентов.',
        },
        'REFERRAL_PROGRAM_ENABLED': {
            'description': 'Общий переключатель реферальной программы. Если выключено, партнерский раздел полностью скрыт.',
            'format': 'Булево значение (Вкл/Выкл).',
            'example': 'Включено',
        },
        'REFERRAL_BUTTON_TEXT': {
            'description': 'Текст, который будет написан на кнопке партнерки в главном меню.',
            'format': 'Текстовая строка.',
            'example': '🤝 Партнерка',
        },
        'REFERRAL_BUTTON_STYLE': {
            'description': 'Цветовое оформление кнопки партнерки в главном меню (для инлайн-кнопок).',
            'format': 'Выберите один из четырех цветов.',
            'example': 'Синий (основной)',
        },
        'REFERRAL_BUTTON_EMOJI': {
            'description': (
                'Позволяет использовать красивый анимированный премиум-эмодзи для партнерки. '
                'Для этого отправьте нужный эмодзи боту @EmojiIdBot и вставьте полученный ID сюда.'
            ),
            'format': 'ID премиум-эмодзи.',
            'warning': 'Будет работать только в официальных приложениях Telegram.',
        },
        'REFERRAL_COMMISSION_PERCENT': {
            'description': 'Процент от суммы пополнения рефералов, который моментально начисляется на баланс пригласившего.',
            'format': 'Целое число от 0 до 100.',
            'example': '25',
            'warning': 'Слишком высокий процент может сделать работу сервиса невыгодной.',
        },
        'REFERRAL_INVITER_BONUS_KOPEKS': {
            'description': 'Фиксированная сумма в копейках, выплачиваемая пригласившему за сам факт регистрации или первого пополнения реферала.',
            'format': 'Целое число в копейках (напр. 10000 = 100 ₽).',
            'example': '10000',
        },
        'REFERRAL_MINIMUM_TOPUP_KOPEKS': {
            'description': 'Минимальная сумма первого пополнения рефералом, необходимая для активации бонусов пригласившего.',
            'format': 'Число в копейках.',
            'example': '10000',
        },

        'AUTO_PURCHASE_AFTER_TOPUP_ENABLED': {
            'description': 'Если у пользователя была выбрана подписка, но не хватало денег, она купится автоматически сразу после пополнения баланса.',
            'format': 'Булево значение.',
        },

        'REFERRAL_CONTESTS_ENABLED': {
            'description': (
                'Включает систему соревнований между вашими партнерами. '
                'После включения в админке появится раздел для создания конкурсов с призами за регистрации или покупки подписок их рефералами.'
            ),
            'format': 'Булево значение.',
            'example': 'Включите, чтобы запустить стимулирующую акцию для рефереров.',
            'warning': 'После включения необходимо зайти в меню «Конкурсы» и создать активный конкурс, иначе система будет простаивать.',
        },

        # SUPPORT
        'SUPPORT_MENU_ENABLED': {
            'description': 'Управляет отображением кнопки «Поддержка» в главном меню бота.',
            'format': 'Булево значение.',
        },
        'SUPPORT_SYSTEM_MODE': {
            'description': 'Выбор режима работы поддержки: через тикеты внутри бота, прямую ссылку на контакт или оба варианта.',
            'format': 'Один из вариантов: tickets, contact, both.',
            'example': 'tickets — работа через систему обращений.',
        },
        'SUPPORT_TICKET_SLA_MINUTES': {
            'description': 'Рекомендуемое время ответа на тикет. Если время превышено, админомодератор получит уведомление.',
            'format': 'Количество минут (напр. 30).',
            'example': '5',
        },

        # TRIAL
        'TRIAL_DURATION_DAYS': {
            'description': 'Количество дней бесплатного пробного периода для новых пользователей.',
            'format': 'Целое число дней.',
            'example': '3',
            'warning': 'Установка 0 отключит триал, если нет других условий.',
        },
        'TRIAL_TRAFFIC_LIMIT_GB': {
            'description': 'Лимит трафика, выдаваемый на пробный период.',
            'format': 'Целое число ГБ.',
            'example': '5',
        },
        'TRIAL_PAYMENT_ENABLED': {
            'description': 'Если включено, активация триала станет платной (символическая сумма для борьбы с фермами).',
            'format': 'Булево значение.',
            'dependencies': 'TRIAL_ACTIVATION_PRICE',
        },

        # DATABASE
        'DATABASE_MODE': {
            'description': 'Выбор типа хранилища данных. Автоматический режим сам определит окружение (Docker/Local).',
            'format': 'auto, sqlite или postgresql.',
            'warning': 'Изменение требует перезагрузки бота и миграции данных.',
        },
        'REDIS_URL': {
            'description': 'Адрес подключения к Redis для кэширования состояний и сессий.',
            'format': 'redis://host:port/db',
            'example': 'redis://localhost:6379/0',
        },

        # REMNAWAVE
        'REMNAWAVE_API_URL': {
            'description': 'Базовый адрес вашей панели управления RemnaWave.',
            'format': 'URL адрес (напр. https://panel.example.com).',
            'example': 'https://my-panel.com',
        },
        'REMNAWAVE_AUTO_SYNC_ENABLED': {
            'description': 'Автоматическая синхронизация статусов подписок и трафика с панелью по расписанию.',
            'format': 'Булево значение.',
            'dependencies': 'REMNAWAVE_AUTO_SYNC_TIMES',
        },


        'TELEGRAM_STARS_ENABLED': {
            'description': 'Позволяет пользователям пополнять баланс через внутреннюю валюту Telegram Stars.',
            'format': 'Булево значение.',
            'warning': 'Взимается комиссия Telegram. Настройка курса Stars производится отдельно.',
        },
        'PAL24_ENABLED': {
            'description': 'Интеграция с платежным шлюзом PayPalych (PAL24) для приема карт и СБП.',
            'format': 'Булево значение.',
        },

        # OTHER PAYMENTS
        'MULENPAY_ENABLED': {
            'description': 'Интеграция с MulenPay для приема платежей.',
            'format': 'Булево значение.',
        },
        'WATA_ENABLED': {
            'description': 'Интеграция с Wata (карты РФ и СБП).',
            'format': 'Булево значение.',
        },
        'CLOUDPAYMENTS_ENABLED': {
            'description': 'Интеграция с CloudPayments (виджет оплаты картами).',
            'format': 'Булево значение.',
        },
        'HELEKET_ENABLED': {
            'description': 'Интеграция с Heleket для приема криптовалюты.',
            'format': 'Булево значение.',
        },
        'TRIBUTE_ENABLED': {
            'description': 'Прием донатов и оплат через сервис Tribute.',
            'format': 'Булево значение.',
        },
        'PRICE_ROUNDING_ENABLED': {
            'description': 'Автоматическое округление цен в интерфейсе (до целого рубля).',
            'format': 'Булево значение.',
            'example': 'Если цена 99.40 руб, станет 99 руб. Если 99.60 руб, станет 100 руб.',
        },
        'PAYMENT_SERVICE_NAME': {
            'description': 'Название вашей услуги, которое будет отображаться в чеках и платежных формах.',
            'format': 'Строка (макс. 64 символа).',
            'example': 'RemnaWave VPN Service',
        },
        'PAYMENT_BALANCE_TEMPLATE': {
            'description': 'Шаблон строки описания платежа при пополнении баланса.',
            'format': 'Строка с поддержкой {service_name} и {description}.',
            'example': '{service_name}: {description}',
        },

        # BACKUP & LOGS
        'BACKUP_AUTO_ENABLED': {
            'description': 'Автоматическое создание резервных копий базы данных по расписанию.',
            'format': 'Булево значение.',
            'dependencies': 'BACKUP_INTERVAL_HOURS, BACKUP_TIME',
        },
        'BACKUP_TIME': {
            'description': 'Точное время суток для запуска процесса резервного копирования.',
            'format': 'Время в формате HH:MM.',
            'example': '03:00',
        },
        'BACKUP_LOCATION': {
            'description': 'Путь к папке внутри сервера, где будут храниться файлы бэкапов.',
            'format': 'Абсолютный или относительный путь.',
            'example': '/app/data/backups',
        },
        'BACKUP_SEND_ENABLED': {
            'description': 'Автоматическая отправка созданного файла бэкапа в Telegram чат или канал.',
            'format': 'Булево значение.',
            'warning': 'Файлы базы данных могут содержать чувствительную информацию. Убедитесь в безопасности чата.',
        },
        'BACKUP_ARCHIVE_PASSWORD': {
            'description': 'Пароль для шифрования архива с резервной копией (для 7zip/zip).',
            'format': 'Строка.',
            'warning': 'Обязательно сохраните этот пароль, иначе восстановить данные будет невозможно.',
        },
        'LOG_ROTATION_ENABLED': {
            'description': 'Включает новую систему автоматической очистки и архивации старых журналов (логов).',
            'format': 'Булево значение.',
            'warning': 'Рекомендуется включить для предотвращения переполнения диска.',
        },
        'LOG_ROTATION_KEEP_DAYS': {
            'description': 'Сколько дней хранить старые файлы логов перед их безвозвратным удалением.',
            'format': 'Количество дней.',
            'example': '7',
        },
        'LOG_DIR': {
            'description': 'Название директории, в которой будут храниться все файлы журналов.',
            'format': 'Название папки (напр. logs).',
            'warning': 'Убедитесь, что у бота есть права на создание этой папки.',
        },
        'LOG_LEVEL': {
            'description': 'Уровень детализации системных логов. Для обычной работы рекомендуется INFO.',
            'format': 'DEBUG, INFO, WARNING, ERROR.',
            'warning': 'Уровень DEBUG может сильно замедлить работу и быстро заполнить диск.',
        },
        'BLACKLIST_CHECK_ENABLED': {
            'description': 'Включает автоматическую проверку пользователей по черным спискам. Если пользователь найден в списке, он будет заблокирован.',
            'format': 'Булево значение.',
        },
        'BLACKLIST_GITHUB_URL': {
            'description': 'URL к файлу со списком ID пользователей (в формате txt или json) на GitHub или другом ресурсе.',
            'format': 'Полная ссылка (URL).',
        },
        'BLACKLIST_UPDATE_INTERVAL_HOURS': {
            'description': 'Как часто бот должен обновлять локальную копию черного списка из внешнего источника.',
            'format': 'Число часов.',
            'example': '24',
        },
        'BLACKLIST_IGNORE_ADMINS': {
            'description': 'Если включено, администраторы бота никогда не будут проверяться по черным спискам.',
            'format': 'Булево значение.',
        },


        'MAINTENANCE_MONITORING_ENABLED': {
            'description': ('Управляет автоматическим запуском мониторинга панели Remnawave при старте бота.'),
            'format': 'Булево значение.',
            'example': 'false',
            'warning': ('При отключении мониторинг можно запустить вручную из панели администратора.'),
            'dependencies': 'MAINTENANCE_CHECK_INTERVAL',
        },
        'MAINTENANCE_RETRY_ATTEMPTS': {
            'description': ('Сколько раз повторять проверку панели Remnawave перед фиксацией недоступности.'),
            'format': 'Целое число не меньше 1.',
            'example': '3',
            'warning': (
                'Большие значения увеличивают время реакции на реальные сбои, но помогают избежать ложных срабатываний.'
            ),
            'dependencies': 'MAINTENANCE_CHECK_INTERVAL',
        },
        'DISPLAY_NAME_BANNED_KEYWORDS': {
            'description': (
                'Список слов и фрагментов, при наличии которых в отображаемом имени пользователь будет заблокирован.'
            ),
            'format': 'Перечислите ключевые слова через запятую или с новой строки.',
            'example': 'support, security, служебн',
            'warning': 'Слишком агрессивные фильтры могут блокировать добросовестных пользователей.',
            'dependencies': 'Фильтр отображаемых имен',
        },

        'REMNAWAVE_AUTO_SYNC_TIMES': {
            'description': ('Список времени в формате HH:MM, когда запускается автосинхронизация в течение суток.'),
            'format': 'Перечислите время через запятую или с новой строки (например, 03:00, 15:00).',
            'example': '03:00, 15:00',
            'warning': (
                'Минимальный интервал между запусками не ограничен, но слишком частые синхронизации нагружают панель.'
            ),
            'dependencies': 'REMNAWAVE_AUTO_SYNC_ENABLED',
        },
        'REMNAWAVE_USER_DESCRIPTION_TEMPLATE': {
            'description': (
                'Шаблон текста, который бот передает в поле Description при создании '
                'или обновлении пользователя в панели RemnaWave.'
            ),
            'format': ('Доступные плейсхолдеры: {full_name}, {username}, {username_clean}, {telegram_id}.'),
            'example': 'Bot user: {full_name} {username}',
            'warning': 'Плейсхолдер {username} автоматически очищается, если у пользователя нет @username.',
        },
        'REMNAWAVE_USER_USERNAME_TEMPLATE': {
            'description': (
                'Шаблон имени пользователя, которое создаётся в панели RemnaWave для телеграм-пользователя.'
            ),
            'format': ('Доступные плейсхолдеры: {full_name}, {username}, {username_clean}, {telegram_id}.'),
            'example': 'vpn_{username_clean}_{telegram_id}',
            'warning': (
                'Недопустимые символы автоматически заменяются на подчёркивания. '
                'Если результат пустой, используется user_{telegram_id}.'
            ),
        },
        'EXTERNAL_ADMIN_TOKEN': {
            'description': 'Приватный токен, который использует внешняя админка для проверки запросов.',
            'format': 'Значение генерируется автоматически из username бота и его токена и доступно только для чтения.',
            'example': 'Генерируется автоматически',
            'warning': 'Токен обновится при смене username или токена бота.',
            'dependencies': 'Username телеграм-бота, токен бота',
        },
        'EXTERNAL_ADMIN_TOKEN_BOT_ID': {
            'description': 'Идентификатор телеграм-бота, с которым связан токен внешней админки.',
            'format': 'Проставляется автоматически после первого запуска и не редактируется вручную.',
            'example': '123456789',
            'warning': 'Несовпадение ID блокирует обновление токена, предотвращая его подмену на другом боте.',
            'dependencies': 'Результат вызова getMe() в Telegram Bot API',
        },
        'TRIAL_USER_TAG': {
            'description': (
                'Тег, который бот передаст пользователю при активации триальной подписки в панели RemnaWave.'
            ),
            'format': 'До 16 символов: заглавные A-Z, цифры и подчёркивание.',
            'example': 'TRIAL_USER',
            'warning': 'Неверный формат будет проигнорирован при создании пользователя.',
            'dependencies': 'Активация триала и включенная интеграция с RemnaWave',
        },
        'PAID_SUBSCRIPTION_USER_TAG': {
            'description': ('Тег, который бот ставит пользователю при покупке платной подписки в панели RemnaWave.'),
            'format': 'До 16 символов: заглавные A-Z, цифры и подчёркивание.',
            'example': 'PAID_USER',
            'warning': 'Если тег не задан или невалиден, существующий тег не будет изменён.',
            'dependencies': 'Оплата подписки и интеграция с RemnaWave',
        },
        'CABINET_REMNA_SUB_CONFIG': {
            'description': (
                'UUID конфигурации страницы подписки из RemnaWave. '
                'Позволяет синхронизировать список приложений напрямую из панели.'
            ),
            'format': 'UUID конфигурации из раздела Subscription Page Configs в RemnaWave.',
            'example': 'd4aa2b8c-9a36-4f31-93a2-6f07dad05fba',
            'warning': 'Убедитесь, что конфигурация существует в панели и содержит нужные приложения.',
            'dependencies': 'Настроенное подключение к RemnaWave API',
        },
        'USE_PREMIUM_EMOJIS': {
            'description': 'Включает глобальную замену стандартных эмодзи на кастомные Premium эмодзи.',
            'format': 'Булево значение.',
            'example': 'true',
            'warning': 'Требуется Premium-статус у аккаунта-владельца бота.',
        },
        'PREMIUM_EMOJIS_DATA': {
            'description': 'Данные маппинга эмодзи в формате JSON (автоматически обновляются через панель настройки эмодзи).',
            'format': 'JSON-строка.',
            'example': '{"✅": "5432345678901234567"}',
            'warning': 'Ручное редактирование не рекомендуется, используйте панель настроек.',
        },
        'TRAFFIC_MONITORING_ENABLED': {
            'description': (
                'Включает автоматический мониторинг трафика пользователей. '
                'Система отслеживает изменения трафика (дельту) и сохраняет snapshot в Redis. '
                'При превышении порогов отправляются уведомления пользователям и админам.'
            ),
            'format': 'Булево значение.',
            'example': 'true',
            'warning': (
                'Требует настроенного подключения к Redis. '
                'При включении будет запущен фоновый мониторинг трафика по расписанию.'
            ),
            'dependencies': 'Redis, TRAFFIC_MONITORING_INTERVAL_HOURS, TRAFFIC_SNAPSHOT_TTL_HOURS',
        },
        'TRAFFIC_MONITORING_INTERVAL_HOURS': {
            'description': (
                'Интервал проверки трафика в часах. '
                'Каждые N часов система проверяет трафик всех активных пользователей и сравнивает с предыдущим snapshot.'
            ),
            'format': 'Целое число часов (минимум 1).',
            'example': '24',
            'warning': (
                'Слишком маленький интервал может создать большую нагрузку на RemnaWave API. '
                'Рекомендуется 24 часа для ежедневного мониторинга.'
            ),
            'dependencies': 'TRAFFIC_MONITORING_ENABLED',
        },
        'TRAFFIC_MONITORED_NODES': {
            'description': (
                'Список UUID нод для мониторинга трафика через запятую. '
                'Если пусто - мониторятся все ноды. '
                'Позволяет ограничить мониторинг только определенными серверами.'
            ),
            'format': 'UUID через запятую или пусто для всех нод.',
            'example': 'd4aa2b8c-9a36-4f31-93a2-6f07dad05fba, a1b2c3d4-5678-90ab-cdef-1234567890ab',
            'warning': 'UUID должны существовать в RemnaWave, иначе мониторинг не будет работать.',
            'dependencies': 'TRAFFIC_MONITORING_ENABLED',
        },
        'TRAFFIC_SNAPSHOT_TTL_HOURS': {
            'description': (
                'Время жизни (TTL) snapshot трафика в Redis в часах. '
                'Snapshot используется для вычисления дельты (изменения трафика) между проверками. '
                'После истечения TTL snapshot удаляется и создается новый.'
            ),
            'format': 'Целое число часов (минимум 1).',
            'example': '24',
            'warning': (
                'TTL должен быть >= интервала мониторинга. '
                'Если TTL меньше интервала, snapshot будет удален до следующей проверки.'
            ),
            'dependencies': 'TRAFFIC_MONITORING_ENABLED, Redis',
        },
        'TRAFFIC_FAST_CHECK_ENABLED': {
            'description': (
                'Включает быструю проверку трафика. '
                'Система сравнивает текущий трафик со snapshot и уведомляет о превышениях дельты.'
            ),
            'format': 'Булево значение.',
            'example': 'true',
            'warning': 'Требует Redis для хранения snapshot. При отключении проверки не выполняются.',
            'dependencies': 'Redis, TRAFFIC_FAST_CHECK_INTERVAL_MINUTES, TRAFFIC_FAST_CHECK_THRESHOLD_GB',
        },
        'TRAFFIC_FAST_CHECK_INTERVAL_MINUTES': {
            'description': 'Интервал быстрой проверки трафика в минутах.',
            'format': 'Целое число минут (минимум 1).',
            'example': '10',
            'warning': 'Слишком малый интервал создаёт нагрузку на Remnawave API.',
            'dependencies': 'TRAFFIC_FAST_CHECK_ENABLED',
        },
        'TRAFFIC_FAST_CHECK_THRESHOLD_GB': {
            'description': 'Порог дельты трафика в ГБ для быстрой проверки. При превышении отправляется уведомление.',
            'format': 'Число с плавающей точкой.',
            'example': '5.0',
            'warning': 'Слишком низкий порог приведёт к частым уведомлениям.',
            'dependencies': 'TRAFFIC_FAST_CHECK_ENABLED',
        },
        'TRAFFIC_DAILY_CHECK_ENABLED': {
            'description': 'Включает суточную проверку трафика через bandwidth-stats API.',
            'format': 'Булево значение.',
            'example': 'true',
            'warning': 'Проверка выполняется в указанное время (TRAFFIC_DAILY_CHECK_TIME).',
            'dependencies': 'TRAFFIC_DAILY_CHECK_TIME, TRAFFIC_DAILY_THRESHOLD_GB',
        },
        'TRAFFIC_DAILY_CHECK_TIME': {
            'description': 'Время суточной проверки трафика в формате HH:MM (UTC).',
            'format': 'Строка времени HH:MM.',
            'example': '00:00',
            'warning': 'Время указывается в UTC.',
            'dependencies': 'TRAFFIC_DAILY_CHECK_ENABLED',
        },
        'TRAFFIC_DAILY_THRESHOLD_GB': {
            'description': 'Порог суточного трафика в ГБ. При превышении за 24 часа отправляется уведомление.',
            'format': 'Число с плавающей точкой.',
            'example': '50.0',
            'warning': 'Учитывается весь трафик за последние 24 часа.',
            'dependencies': 'TRAFFIC_DAILY_CHECK_ENABLED',
        },
        'TRAFFIC_NOTIFICATION_COOLDOWN_MINUTES': {
            'description': 'Кулдаун уведомлений по одному пользователю в минутах.',
            'format': 'Целое число минут.',
            'example': '60',
            'warning': 'Защита от спама уведомлениями по одному и тому же пользователю.',
        },
        'WEBHOOK_NOTIFY_USER_ENABLED': {
            'description': (
                'Глобальный переключатель уведомлений пользователям от вебхуков RemnaWave. '
                'При выключении ни одно уведомление не отправляется, независимо от остальных настроек.'
            ),
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_SUB_STATUS': {
            'description': 'Уведомления об отключении и активации подписки администратором.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_SUB_EXPIRED': {
            'description': 'Уведомления об истечении подписки.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_SUB_EXPIRING': {
            'description': 'Предупреждения о скором истечении подписки (72ч, 48ч, 24ч до окончания).',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_SUB_LIMITED': {
            'description': 'Уведомление при достижении лимита трафика.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_TRAFFIC_RESET': {
            'description': 'Уведомление о сбросе счётчика трафика.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_SUB_DELETED': {
            'description': 'Уведомление при удалении пользователя из панели.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_SUB_REVOKED': {
            'description': 'Уведомление при обновлении ключей подписки (revoke).',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_FIRST_CONNECTED': {
            'description': 'Уведомление при первом подключении к VPN.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_NOT_CONNECTED': {
            'description': 'Напоминание, что пользователь ещё не подключился к VPN.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_BANDWIDTH_THRESHOLD': {
            'description': 'Предупреждение при приближении к лимиту трафика (порог в %).',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'WEBHOOK_NOTIFY_DEVICES': {
            'description': 'Уведомления о подключении и отключении устройств.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'RESET_TRAFFIC_ON_TARIFF_SWITCH': {
            'description': (
                'Автоматически сбрасывает счётчик использованного трафика '
                'при переключении пользователя на другой тарифный план. '
                'Сброс происходит через RemnaWave API.'
            ),
            'format': 'Булево значение: выберите "Включить" или "Выключить".',
            'example': 'Включено — трафик обнуляется при каждой смене тарифа.',
            'warning': 'При отключении использованный трафик сохранится после смены тарифа.',
        },
        'RESET_TRAFFIC_ON_PAYMENT': {
            'description': (
                'Автоматически сбрасывает счётчик использованного трафика '
                'при любой оплате или продлении подписки.'
            ),
            'format': 'Булево значение.',
            'example': 'true',
        },
        'YOOKASSA_RETURN_URL': {
            'description': 'Ссылка, на которую бот перенаправит пользователя сразу после успешной оплаты. Обычно это ссылка на сам бот (https://t.me/your_bot), чтобы пользователь мог сразу продолжить работу.',
            'format': 'Веб-ссылка (URL).',
            'example': 'https://t.me/my_vpn_bot',
        },
        'CRYPTOBOT_WEBHOOK_SECRET': {
            'description': 'Важнейший секретный ключ для защиты платежей через CryptoBot. Он позволяет боту убедиться, что уведомление об оплате пришло именно от CryptoBot, а не от злоумышленников.',
            'format': 'Секретная строка из настроек CryptoBot App.',
            'warning': 'Никогда не передавайте этот ключ третьим лицам.',
        },
        'FREEKASSA_API_KEY': {
            'description': 'Служебный ключ для взаимодействия с вашим аккаунтом Freekassa. Позволяет боту автоматически проверять статусы ваших платежей через API v1.',
            'format': 'Секретный API ключ.',
        },
        'NALOGO_INN': {
            'description': 'Ваш ИНН самозанятого. Бот будет использовать его для автоматической регистрации доходов и выписки чеков пользователям через официальный сервис налоговой.',
            'format': '12 цифр без пробелов.',
            'example': '771234567890',
        },
        'NALOGO_PASSWORD': {
            'description': 'Пароль, который вы используете для входа в личный кабинет налогоплательщика «Мой Налог». Это необходимо для автоматической авторизации бота.',
            'format': 'Секретная строка.',
            'warning': 'Указывайте пароль именно от кабинета lkfl.nalog.ru, а не от портала Госуслуг.',
        },
        'WEB_API_HOST': {
            'description': 'Сетевой адрес, на котором будет «слушать» внешние запросы программный интерфейс бота (Web API). Это необходимо для интеграции с внешними панелями управления или сайтами.',
            'format': 'IP-адрес. Оставьте 0.0.0.0, чтобы API был доступен извне.',
            'example': '0.0.0.0',
            'warning': 'Изменение этого параметра может привести к недоступности внешней админ-панели.',
        },
        'WEB_API_PORT': {
            'description': 'Порт, который бот забронирует за своим Web API. По этому порту внешние сервисы будут обращаться к боту.',
            'format': 'Число (рекомендуется выше 1024).',
            'example': '8080',
        },
        'OAUTH_YANDEX_ENABLED': {
            'description': 'Позволяет пользователям быстро регистрироваться и входить в Личный Кабинет через аккаунт Яндекс ID. Это значительно упрощает жизнь тем, кто не хочет запоминать лишние пароли.',
            'format': 'Выберите "Включить", предварительно создав приложение в консоли Яндекс ID.',
            'dependencies': 'OAUTH_YANDEX_CLIENT_ID, OAUTH_YANDEX_CLIENT_SECRET',
        },
        'SERVER_STATUS_MODE': {
            'description': 'Определяет, как пользователи будут видеть статус ваших серверов. «Выключено» — скрыть раздел, «Внешняя ссылка» — направить на ваш сайт мониторинга, «XRay Checker» — запустить встроенную проверку нод в реальном времени.',
            'format': 'Выберите один из трех режимов.',
            'example': 'xray — рекомендуется для максимальной наглядности.',
            'warning': 'Режим XRay Checker работает только при активном соединении с API RemnaWave.',
        },
        'SERVER_STATUS_EXTERNAL_URL': {
            'description': 'Если вы используете сторонние сервисы (например, UptimeRobot или Grafana), укажите ссылку на них здесь. Она превратится в кнопку в меню статуса.',
            'format': 'Полная ссылка на сайт.',
            'example': 'https://status.my-proxy.com',
        },
        'SERVER_STATUS_REQUEST_TIMEOUT': {
            'description': 'Максимальное время, которое бот готов ждать ответа от сервера метрик. Если сервер не ответит вовремя, бот пометит его как «недоступен».',
            'format': 'Число в секундах.',
            'example': '10',
        },
        'WEB_API_ALLOWED_ORIGINS': {
            'description': 'Список доверенных сайтов (доменов), которым разрешено обращаться к вашему Web API. Это защита от выполнения нежелательных скриптов с чужих ресурсов.',
            'format': 'Домены через запятую или знак * для доступа отовсюду.',
            'example': 'https://admin.my-panel.ru, https://dashboard.com',
            'warning': 'Значение * делает API уязвимым, используйте только для отладки.',
        },
        'WEB_API_DEFAULT_TOKEN': {
            'description': 'Секретный пароль (токен) для авторизации внешних инструментов в вашем API. Бот будет сравнивать этот ключ с присылаемым, чтобы отсечь неавторизованные запросы.',
            'format': 'Длинная случайная строка.',
            'warning': 'Утрата или утечка этого токена дает полный контроль над API вашего бота.',
        },
        'MAINTENANCE_CHECK_INTERVAL': {
            'description': 'Как часто бот должен обращаться к панели RemnaWave, чтобы проверить её "самочувствие". Если панель не ответит, бот поймет, что случился сбой.',
            'format': 'Время в секундах.',
            'example': '30',
        },
        'MAINTENANCE_AUTO_ENABLE': {
            'description': 'Умный режим защиты: если бот обнаружит, что панель RemnaWave недоступна (например, из-за аварии на сервере), он сам включит "Режим тех. работ". Это нужно, чтобы пользователи не могли оплатить услуги, которые бот временно не может активировать.',
            'format': 'Включите для автоматической защиты транзакций.',
            'warning': 'При включении пользователи могут увидеть сообщение о тех. работах до того, как вы узнаете о сбое.',
        },
        'OAUTH_DISCORD_ENABLED': {
            'description': 'Включает авторизацию в кабинете через Discord ID. Позволяет вашим пользователям использовать свои игровые аккаунты для входа.',
            'format': 'Включите после настройки Client ID/Secret в панели разработчика Discord.',
            'dependencies': 'OAUTH_DISCORD_CLIENT_ID, OAUTH_DISCORD_CLIENT_SECRET',
        },
        'OAUTH_VK_ENABLED': {
            'description': 'Разрешает вход в Личный Кабинет через соцсеть ВКонтакте. Максимально привычный способ авторизации для пользователей из СНГ.',
            'format': 'Включите, если у вас создано приложение в VK Dev.',
            'dependencies': 'OAUTH_VK_CLIENT_ID, OAUTH_VK_CLIENT_SECRET',
        },
        'CABINET_JWT_SECRET': {
            'description': 'Сверхсекретный ключ, которым бот "запечатывает" сессии пользователей в кабинете. Он защищает данные от подделки.',
            'format': 'Случайный набор символов (чем длиннее, тем лучше).',
            'warning': 'Если вы измените этот ключ, ВСЕ активные сессии пользователей будут прерваны, и им придется входить заново.',
        },
        'GIFTS_ENABLED': {
            'description': 'Основной переключатель системы подарков. Позволяет пользователям покупать VPN-подписки не только для себя, но и в качестве подарка другим людям.',
            'format': 'Включите, чтобы запустить функционал подарков.',
            'example': 'true',
            'warning': 'При отключении раздел покупки подарков исчезнет у всех пользователей.',
        },
        'GIFTS_BUTTON_VISIBLE': {
            'description': 'Управляет видимостью кнопки «🎁 Подарить VPN» в главном меню. Вы можете временно скрыть её, не выключая саму систему подарков.',
            'format': 'Булево значение.',
            'example': 'true',
        },
        'GIFTS_BUTTON_TEXT': {
            'description': 'Текст, который будет написан на кнопке подарков. Сделайте его привлекательным, чтобы пользователи чаще делали подарки.',
            'format': 'Яркая текстовая строка.',
            'example': '🎁 Подарить другу VPN',
        },
        'GIFTS_BUTTON_STYLE': {
            'description': 'Цветовое оформление кнопки подарков в главном меню. Рекомендуется использовать «Зеленый», чтобы выделить её на фоне остальных.',
            'format': 'Выберите один из четырех цветов.',
            'example': 'Зелёный',
        },
        'GIFTS_BUTTON_EMOJI': {
            'description': (
                'Позволяет использовать красивый анимированный премиум-эмодзи вместо стандартного 🎁. '
                'Для этого отправьте нужный эмодзи боту @EmojiIdBot и вставьте полученный ID сюда.'
            ),
            'format': 'ID премиум-эмодзи.',
            'warning': 'Будет работать только в официальных приложениях Telegram.',
        },
        'GIFTS_SHARE_MESSAGE_TEMPLATE': {
            'description': 'Текст сообщения, которое бот предложит пользователю скопировать после покупки подарка. Это сообщение он отправит другу в личку.',
            'format': 'Используйте {link} — на это место бот подставит уникальную ссылку на активацию.',
            'example': 'Бро, лови подарок! Активируй свой VPN тут: {link}',
        },
        'NALOGO_ENABLED': {
            'description': 'Включает автоматизированную отчетность для самозанятых через NaloGO. Бот будет сам создавать записи о доходах в приложении «Мой Налог».',
            'format': 'Включите для авто-выписки чеков.',
            'warning': 'Требуется предварительная настройка ИНН и пароля.',
        },
        'NALOGO_QUEUE_CHECK_INTERVAL': {
            'description': 'Как часто (в секундах) бот будет проверять «очередь» новых платежей для их фискализации. Оптимально — 60 секунд.',
            'format': 'Число.',
            'example': '60',
        },
        'NALOGO_QUEUE_RECEIPT_DELAY': {
            'description': 'Небольшая пауза между отправкой чеков в налоговую. Это нужно, чтобы сервера налоговой не сочли активность бота за спам-атаку.',
            'format': 'Число в секундах.',
            'example': '5',
        },

    }

    @classmethod
    def get_category_description(cls, category_key: str) -> str:
        description = cls.CATEGORY_DESCRIPTIONS.get(category_key, '')
        return cls._format_dynamic_copy(category_key, description)

    @classmethod
    def is_toggle(cls, key: str) -> bool:
        definition = cls.get_definition(key)
        return definition.python_type is bool

    @classmethod
    def is_read_only(cls, key: str) -> bool:
        return key in cls.READ_ONLY_KEYS

    @classmethod
    def _is_env_override(cls, key: str) -> bool:
        return key in cls._env_override_keys

    @classmethod
    def _format_numeric_with_unit(cls, key: str, value: float) -> str | None:
        if isinstance(value, bool):
            return None
        upper_key = key.upper()
        if any(suffix in upper_key for suffix in ('PRICE', '_KOPEKS', 'AMOUNT')):
            try:
                return settings.format_price(int(value))
            except Exception:
                return f'{value}'
        if upper_key.endswith('_PERCENT') or 'PERCENT' in upper_key:
            return f'{value}%'
        if upper_key.endswith('_HOURS'):
            return f'{value} ч'
        if upper_key.endswith('_MINUTES'):
            return f'{value} мин'
        if upper_key.endswith('_SECONDS'):
            return f'{value} сек'
        if upper_key.endswith('_DAYS'):
            return f'{value} дн'
        if upper_key.endswith('_GB'):
            return f'{value} ГБ'
        if upper_key.endswith('_MB'):
            return f'{value} МБ'
        return None

    @classmethod
    def _split_comma_values(cls, text: str) -> list[str] | None:
        raw = (text or '').strip()
        if not raw or ',' not in raw:
            return None
        parts = [segment.strip() for segment in raw.split(',') if segment.strip()]
        return parts or None

    @classmethod
    def format_value_human(cls, key: str, value: Any) -> str:
        if key == 'SIMPLE_SUBSCRIPTION_SQUAD_UUID':
            if value is None:
                return 'Любой доступный'
            if isinstance(value, str):
                cleaned_value = value.strip()
                if not cleaned_value:
                    return 'Любой доступный'

        if value is None:
            return '—'

        if isinstance(value, bool):
            return '✅ ВКЛЮЧЕНО' if value else '❌ ВЫКЛЮЧЕНО'

        if isinstance(value, (int, float)):
            formatted = cls._format_numeric_with_unit(key, value)
            return formatted or str(value)

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return '—'
            if key in cls.PLAIN_TEXT_KEYS:
                return cleaned
            if any(keyword in key.upper() for keyword in ('TOKEN', 'SECRET', 'PASSWORD', 'KEY')):
                return '••••••••'
            items = cls._split_comma_values(cleaned)
            if items:
                return ', '.join(items)
            return cleaned

        if isinstance(value, (list, tuple, set)):
            return ', '.join(str(item) for item in value)

        if isinstance(value, dict):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)

        return str(value)

    @classmethod
    def get_setting_guidance(cls, key: str) -> dict[str, str]:
        definition = cls.get_definition(key)
        original = cls.get_original_value(key)
        type_label = definition.type_label
        hints = dict(cls.SETTING_HINTS.get(key, {}))

        base_description = (
            hints.get('description')
            or f'Параметр <b>{definition.display_name}</b> управляет категорией «{definition.category_label}».'
        )
        base_format = hints.get('format') or (
            'Булево значение (да/нет).'
            if definition.python_type is bool
            else 'Введите значение соответствующего типа (число или строку).'
        )
        example = hints.get('example') or (cls.format_value_human(key, original) if original is not None else '—')
        warning = hints.get('warning') or ('Неверные значения могут привести к некорректной работе бота.')
        dependencies = hints.get('dependencies') or definition.category_label

        return {
            'description': base_description,
            'format': base_format,
            'example': example,
            'warning': warning,
            'dependencies': dependencies,
            'type': type_label,
        }

    _definitions: dict[str, SettingDefinition] = {}
    _original_values: dict[str, Any] = settings.model_dump()
    _overrides_raw: dict[str, str | None] = {}
    _env_override_keys: set[str] = set(ENV_OVERRIDE_KEYS)
    _callback_tokens: dict[str, str] = {}
    _token_to_key: dict[str, str] = {}
    _choice_tokens: dict[str, dict[Any, str]] = {}
    _choice_token_lookup: dict[str, dict[str, Any]] = {}

    @classmethod
    def initialize_definitions(cls) -> None:
        if cls._definitions:
            return

        for key, field in Settings.model_fields.items():
            if key in cls.EXCLUDED_KEYS:
                continue

            annotation = field.annotation
            python_type, is_optional = cls._normalize_type(annotation)
            type_label = cls._type_to_label(python_type, is_optional)

            category_key = cls._resolve_category_key(key)
            category_label = cls.CATEGORY_TITLES.get(
                category_key,
                category_key.capitalize() if category_key else 'Прочее',
            )
            category_label = cls._format_dynamic_copy(category_key, category_label)

            cls._definitions[key] = SettingDefinition(
                key=key,
                category_key=category_key or 'other',
                category_label=category_label,
                python_type=python_type,
                type_label=type_label,
                is_optional=is_optional,
            )

            cls._register_callback_token(key)
            if key in cls.CHOICES:
                cls._ensure_choice_tokens(key)

    @classmethod
    def _resolve_category_key(cls, key: str) -> str:
        override = cls.CATEGORY_KEY_OVERRIDES.get(key)
        if override:
            return override

        for prefix, category in sorted(
            cls.CATEGORY_PREFIX_OVERRIDES.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if key.startswith(prefix):
                return category

        if '_' not in key:
            return key.upper()
        prefix = key.split('_', 1)[0]
        return prefix.upper()

    @classmethod
    def _normalize_type(cls, annotation: Any) -> tuple[type[Any], bool]:
        if annotation is None:
            return str, True

        origin = get_origin(annotation)
        if origin is Union:
            args = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(args) == 1:
                nested_type, nested_optional = cls._normalize_type(args[0])
                return nested_type, True
            return str, True

        if annotation in {int, float, bool, str}:
            return annotation, False

        if annotation in {Optional[int], Optional[float], Optional[bool], Optional[str]}:
            nested = get_args(annotation)[0]
            return nested, True

        # Paths, lists, dicts и прочее будем хранить как строки
        return str, False

    @classmethod
    def _type_to_label(cls, python_type: type[Any], is_optional: bool) -> str:
        base = {
            bool: 'bool',
            int: 'int',
            float: 'float',
            str: 'str',
        }.get(python_type, 'str')
        return f'optional[{base}]' if is_optional else base

    @classmethod
    def get_categories(cls) -> list[tuple[str, str, int]]:
        cls.initialize_definitions()
        categories: dict[str, list[SettingDefinition]] = {}

        for definition in cls._definitions.values():
            categories.setdefault(definition.category_key, []).append(definition)

        result: list[tuple[str, str, int]] = []
        for category_key, items in categories.items():
            label = items[0].category_label
            result.append((category_key, label, len(items)))

        result.sort(key=lambda item: item[1])
        return result

    @classmethod
    def get_settings_for_category(cls, category_key: str) -> list[SettingDefinition]:
        cls.initialize_definitions()
        filtered = [definition for definition in cls._definitions.values() if definition.category_key == category_key]
        filtered.sort(key=lambda definition: definition.key)
        return filtered

    @classmethod
    def get_definition(cls, key: str) -> SettingDefinition:
        cls.initialize_definitions()
        return cls._definitions[key]

    @classmethod
    def has_override(cls, key: str) -> bool:
        if cls._is_env_override(key):
            return False
        return key in cls._overrides_raw

    @classmethod
    def get_current_value(cls, key: str) -> Any:
        return getattr(settings, key)

    @classmethod
    def get_original_value(cls, key: str) -> Any:
        return cls._original_values.get(key)

    @classmethod
    def format_value(cls, value: Any) -> str:
        if value is None:
            return '—'
        if isinstance(value, bool):
            return '✅ Да' if value else '❌ Нет'
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, dict, tuple, set)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        return str(value)

    @classmethod
    def format_value_for_list(cls, key: str) -> str:
        value = cls.get_current_value(key)
        formatted = cls.format_value_human(key, value)
        if formatted == '—':
            return formatted
        return _truncate(formatted)

    @classmethod
    def get_choice_options(cls, key: str) -> list[ChoiceOption]:
        cls.initialize_definitions()
        dynamic = cls._get_dynamic_choice_options(key)
        if dynamic is not None:
            cls.CHOICES[key] = dynamic
            cls._invalidate_choice_cache(key)
            return dynamic
        return cls.CHOICES.get(key, [])

    @classmethod
    def _invalidate_choice_cache(cls, key: str) -> None:
        cls._choice_tokens.pop(key, None)
        cls._choice_token_lookup.pop(key, None)

    @classmethod
    def _get_dynamic_choice_options(cls, key: str) -> list[ChoiceOption] | None:
        if key == 'SIMPLE_SUBSCRIPTION_PERIOD_DAYS':
            return cls._build_simple_subscription_period_choices()
        if key == 'SIMPLE_SUBSCRIPTION_DEVICE_LIMIT':
            return cls._build_simple_subscription_device_choices()
        if key == 'SIMPLE_SUBSCRIPTION_TRAFFIC_GB':
            return cls._build_simple_subscription_traffic_choices()
        return None

    @staticmethod
    def _build_simple_subscription_period_choices() -> list[ChoiceOption]:
        raw_periods = str(getattr(settings, 'AVAILABLE_SUBSCRIPTION_PERIODS', '') or '')
        period_values: set[int] = set()

        for segment in raw_periods.split(','):
            segment = segment.strip()
            if not segment:
                continue
            try:
                period = int(segment)
            except ValueError:
                continue
            if period > 0:
                period_values.add(period)

        fallback_period = getattr(settings, 'SIMPLE_SUBSCRIPTION_PERIOD_DAYS', 30) or 30
        try:
            fallback_period = int(fallback_period)
        except (TypeError, ValueError):
            fallback_period = 30
        period_values.add(max(1, fallback_period))

        options: list[ChoiceOption] = []
        for days in sorted(period_values):
            price_attr = f'PRICE_{days}_DAYS'
            price_value = getattr(settings, price_attr, None)
            if not isinstance(price_value, int):
                price_value = settings.BASE_SUBSCRIPTION_PRICE

            label = f'{days} дн.'
            try:
                if isinstance(price_value, int):
                    label = f'{label} — {settings.format_price(price_value)}'
            except Exception:
                logger.debug('Не удалось форматировать цену для периода', days=days, exc_info=True)

            options.append(ChoiceOption(days, label))

        return options

    @classmethod
    def _build_simple_subscription_device_choices(cls) -> list[ChoiceOption]:
        default_limit = getattr(settings, 'DEFAULT_DEVICE_LIMIT', 1) or 1
        try:
            default_limit = int(default_limit)
        except (TypeError, ValueError):
            default_limit = 1

        max_limit = getattr(settings, 'MAX_DEVICES_LIMIT', default_limit) or default_limit
        try:
            max_limit = int(max_limit)
        except (TypeError, ValueError):
            max_limit = default_limit

        current_limit = getattr(settings, 'SIMPLE_SUBSCRIPTION_DEVICE_LIMIT', default_limit) or default_limit
        try:
            current_limit = int(current_limit)
        except (TypeError, ValueError):
            current_limit = default_limit

        upper_bound = max(default_limit, max_limit, current_limit, 1)
        upper_bound = min(max(upper_bound, 1), 50)

        options: list[ChoiceOption] = []
        for count in range(1, upper_bound + 1):
            label = f'{count} {cls._pluralize_devices(count)}'
            if count == default_limit:
                label = f'{label} (по умолчанию)'
            options.append(ChoiceOption(count, label))

        return options

    @staticmethod
    def _build_simple_subscription_traffic_choices() -> list[ChoiceOption]:
        try:
            packages = settings.get_traffic_packages()
        except Exception as error:
            logger.warning('Не удалось получить пакеты трафика', error=error, exc_info=True)
            packages = []

        traffic_values: set[int] = {0}
        for package in packages:
            gb_value = package.get('gb')
            try:
                gb = int(gb_value)
            except (TypeError, ValueError):
                continue
            if gb >= 0:
                traffic_values.add(gb)

        default_limit = getattr(settings, 'DEFAULT_TRAFFIC_LIMIT_GB', 0) or 0
        try:
            default_limit = int(default_limit)
        except (TypeError, ValueError):
            default_limit = 0
        if default_limit >= 0:
            traffic_values.add(default_limit)

        current_limit = getattr(settings, 'SIMPLE_SUBSCRIPTION_TRAFFIC_GB', default_limit)
        try:
            current_limit = int(current_limit)
        except (TypeError, ValueError):
            current_limit = default_limit
        if current_limit >= 0:
            traffic_values.add(current_limit)

        options: list[ChoiceOption] = []
        for gb in sorted(traffic_values):
            if gb <= 0:
                label = 'Безлимит'
            else:
                label = f'{gb} ГБ'

            price_label = None
            for package in packages:
                try:
                    package_gb = int(package.get('gb'))
                except (TypeError, ValueError):
                    continue
                if package_gb != gb:
                    continue
                price_raw = package.get('price')
                try:
                    price_value = int(price_raw)
                    if price_value >= 0:
                        price_label = settings.format_price(price_value)
                except (TypeError, ValueError):
                    continue
                break

            if price_label:
                label = f'{label} — {price_label}'

            options.append(ChoiceOption(gb, label))

        return options

    @staticmethod
    def _pluralize_devices(count: int) -> str:
        count = abs(int(count))
        last_two = count % 100
        last_one = count % 10
        if 11 <= last_two <= 14:
            return 'устройств'
        if last_one == 1:
            return 'устройство'
        if 2 <= last_one <= 4:
            return 'устройства'
        return 'устройств'

    @classmethod
    def has_choices(cls, key: str) -> bool:
        return bool(cls.get_choice_options(key))

    @classmethod
    def get_callback_token(cls, key: str) -> str:
        cls.initialize_definitions()
        return cls._callback_tokens[key]

    @classmethod
    def resolve_callback_token(cls, token: str) -> str:
        cls.initialize_definitions()
        return cls._token_to_key[token]

    @classmethod
    def get_choice_token(cls, key: str, value: Any) -> str | None:
        cls.initialize_definitions()
        cls._ensure_choice_tokens(key)
        return cls._choice_tokens.get(key, {}).get(value)

    @classmethod
    def resolve_choice_token(cls, key: str, token: str) -> Any:
        cls.initialize_definitions()
        cls._ensure_choice_tokens(key)
        return cls._choice_token_lookup.get(key, {})[token]

    @classmethod
    def _register_callback_token(cls, key: str) -> None:
        if key in cls._callback_tokens:
            return

        base = hashlib.blake2s(key.encode('utf-8'), digest_size=6).hexdigest()
        candidate = base
        counter = 1
        while candidate in cls._token_to_key and cls._token_to_key[candidate] != key:
            suffix = cls._encode_base36(counter)
            candidate = f'{base}{suffix}'[:16]
            counter += 1

        cls._callback_tokens[key] = candidate
        cls._token_to_key[candidate] = key

    @classmethod
    def _ensure_choice_tokens(cls, key: str) -> None:
        if key in cls._choice_tokens:
            return

        options = cls.CHOICES.get(key, [])
        value_to_token: dict[Any, str] = {}
        token_to_value: dict[str, Any] = {}

        for index, option in enumerate(options):
            token = cls._encode_base36(index)
            value_to_token[option.value] = token
            token_to_value[token] = option.value

        cls._choice_tokens[key] = value_to_token
        cls._choice_token_lookup[key] = token_to_value

    @staticmethod
    def _encode_base36(number: int) -> str:
        if number < 0:
            raise ValueError('number must be non-negative')
        alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
        if number == 0:
            return '0'
        result = []
        while number:
            number, rem = divmod(number, 36)
            result.append(alphabet[rem])
        return ''.join(reversed(result))

    @classmethod
    async def initialize(cls) -> None:
        cls.initialize_definitions()

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SystemSetting))
            rows = result.scalars().all()

        overrides: dict[str, str | None] = {}
        for row in rows:
            if row.key in cls._definitions:
                overrides[row.key] = row.value

        for key, raw_value in overrides.items():
            if cls._is_env_override(key) and key not in {'SUPPORT_AI_ENABLED', 'SUPPORT_AI_FORUM_ID'}:
                logger.debug('Пропускаем настройку из БД: используется значение из окружения', key=key)
                continue
            try:
                parsed_value = cls.deserialize_value(key, raw_value)
            except Exception as error:
                logger.error('Не удалось применить настройку', key=key, error=error)
                continue

            cls._overrides_raw[key] = raw_value
            cls._apply_to_settings(key, parsed_value)

        await cls._sync_default_web_api_token()

    @classmethod
    async def reload(cls) -> None:
        cls._overrides_raw.clear()
        await cls.initialize()

    @classmethod
    def deserialize_value(cls, key: str, raw_value: str | None) -> Any:
        if raw_value is None:
            return None

        definition = cls.get_definition(key)
        python_type = definition.python_type

        if python_type is bool:
            value_lower = raw_value.strip().lower()
            if value_lower in {'1', 'true', 'on', 'yes', 'да'}:
                return True
            if value_lower in {'0', 'false', 'off', 'no', 'нет'}:
                return False
            raise ValueError(f'Неверное булево значение: {raw_value}')

        if python_type is int:
            return int(raw_value)

        if python_type is float:
            return float(raw_value)

        return raw_value

    @classmethod
    def serialize_value(cls, key: str, value: Any) -> str | None:
        if value is None:
            return None

        definition = cls.get_definition(key)
        python_type = definition.python_type

        if python_type is bool:
            return 'true' if value else 'false'
        if python_type in {int, float}:
            return str(value)
        return str(value)

    @classmethod
    def parse_user_value(cls, key: str, user_input: str) -> Any:
        definition = cls.get_definition(key)
        text = (user_input or '').strip()

        if text.lower() in {'отмена', 'cancel'}:
            raise ValueError('Ввод отменен пользователем')

        if definition.is_optional and text.lower() in {'none', 'null', 'пусто', ''}:
            return None

        python_type = definition.python_type

        if python_type is bool:
            lowered = text.lower()
            if lowered in {'1', 'true', 'on', 'yes', 'да', 'вкл', 'enable', 'enabled'}:
                return True
            if lowered in {'0', 'false', 'off', 'no', 'нет', 'выкл', 'disable', 'disabled'}:
                return False
            raise ValueError("Введите 'true' или 'false' (или 'да'/'нет')")

        if python_type is int:
            parsed_value: Any = int(text)
        elif python_type is float:
            parsed_value = float(text.replace(',', '.'))
        else:
            parsed_value = text

        choices = cls.get_choice_options(key)
        if choices:
            allowed_values = {option.value for option in choices}
            if python_type is str:
                lowered_map = {str(option.value).lower(): option.value for option in choices}
                normalized = lowered_map.get(str(parsed_value).lower())
                if normalized is not None:
                    parsed_value = normalized
                elif parsed_value not in allowed_values:
                    readable = ', '.join(f'{option.label} ({cls.format_value(option.value)})' for option in choices)
                    raise ValueError(f'Доступные значения: {readable}')
            elif parsed_value not in allowed_values:
                readable = ', '.join(f'{option.label} ({cls.format_value(option.value)})' for option in choices)
                raise ValueError(f'Доступные значения: {readable}')

        return parsed_value

    @classmethod
    async def set_value(
        cls,
        db: AsyncSession,
        key: str,
        value: Any,
        *,
        force: bool = False,
    ) -> None:
        if cls.is_read_only(key) and not force:
            raise ReadOnlySettingError(f'Setting {key} is read-only')

        raw_value = cls.serialize_value(key, value)
        await upsert_system_setting(db, key, raw_value)
        if cls._is_env_override(key):
            logger.info('Настройка сохранена в БД, но не применена: значение задаётся через окружение', key=key)
            cls._overrides_raw.pop(key, None)
        else:
            cls._overrides_raw[key] = raw_value
            cls._apply_to_settings(key, value)

        if key in {'WEB_API_DEFAULT_TOKEN', 'WEB_API_DEFAULT_TOKEN_NAME'}:
            await cls._sync_default_web_api_token()

    @classmethod
    async def reset_value(
        cls,
        db: AsyncSession,
        key: str,
        *,
        force: bool = False,
    ) -> None:
        if cls.is_read_only(key) and not force:
            raise ReadOnlySettingError(f'Setting {key} is read-only')

        await delete_system_setting(db, key)
        cls._overrides_raw.pop(key, None)
        if cls._is_env_override(key):
            logger.info('Настройка сброшена в БД, используется значение из окружения', key=key)
        else:
            original = cls.get_original_value(key)
            cls._apply_to_settings(key, original)

        if key in {'WEB_API_DEFAULT_TOKEN', 'WEB_API_DEFAULT_TOKEN_NAME'}:
            await cls._sync_default_web_api_token()

    @classmethod
    def _apply_to_settings(cls, key: str, value: Any) -> None:
        if cls._is_env_override(key):
            # Allow DB overrides for critical AI ticket settings
            if key not in {'SUPPORT_AI_ENABLED', 'SUPPORT_AI_FORUM_ID'}:
                logger.debug('Пропуск применения настройки: значение задано через окружение', key=key)
                return
            logger.info('Применяем настройку из БД поверх .env (приоритет для ИИ)', key=key)
        try:
            setattr(settings, key, value)
            if key in {
                'PRICE_14_DAYS',
                'PRICE_30_DAYS',
                'PRICE_60_DAYS',
                'PRICE_90_DAYS',
                'PRICE_180_DAYS',
                'PRICE_360_DAYS',
            }:
                refresh_period_prices()
            elif key.startswith('PRICE_TRAFFIC_') or key == 'TRAFFIC_PACKAGES_CONFIG':
                refresh_traffic_prices()
            elif key in {'REMNAWAVE_AUTO_SYNC_ENABLED', 'REMNAWAVE_AUTO_SYNC_TIMES'}:
                try:
                    from app.services.remnawave_sync_service import remnawave_sync_service

                    remnawave_sync_service.schedule_refresh(
                        run_immediately=(key == 'REMNAWAVE_AUTO_SYNC_ENABLED' and bool(value))
                    )
                except Exception as error:
                    logger.error('Не удалось обновить сервис автосинхронизации RemnaWave', error=error)
            elif key == 'SUPPORT_SYSTEM_MODE':
                try:
                    from app.services.support_settings_service import SupportSettingsService

                    SupportSettingsService.set_system_mode(str(value))
                except Exception as error:
                    logger.error('Не удалось синхронизировать SupportSettingsService', error=error)
            elif key in {
                'REMNAWAVE_API_URL',
                'REMNAWAVE_API_KEY',
                'REMNAWAVE_SECRET_KEY',
                'REMNAWAVE_USERNAME',
                'REMNAWAVE_PASSWORD',
                'REMNAWAVE_AUTH_TYPE',
            }:
                try:
                    from app.services.remnawave_sync_service import remnawave_sync_service

                    remnawave_sync_service.refresh_configuration()
                except Exception as error:
                    logger.error('Не удалось обновить конфигурацию сервиса автосинхронизации RemnaWave', error=error)
        except Exception as error:
            logger.error('Не удалось применить значение', key=key, setting_value=value, error=error)

    @staticmethod
    async def _sync_default_web_api_token() -> None:
        default_token = (settings.WEB_API_DEFAULT_TOKEN or '').strip()
        if not default_token:
            return

        success = await ensure_default_web_api_token()
        if not success:
            logger.warning(
                'Не удалось синхронизировать бутстрап токен веб-API после обновления настроек',
            )

    @classmethod
    def get_setting_summary(cls, key: str) -> dict[str, Any]:
        definition = cls.get_definition(key)
        current = cls.get_current_value(key)
        original = cls.get_original_value(key)
        has_override = cls.has_override(key)

        return {
            'key': key,
            'name': definition.display_name,
            'current': cls.format_value_human(key, current),
            'original': cls.format_value_human(key, original),
            'type': definition.type_label,
            'category_key': definition.category_key,
            'category_label': definition.category_label,
            'has_override': has_override,
            'is_read_only': cls.is_read_only(key),
        }


bot_configuration_service = BotConfigurationService
