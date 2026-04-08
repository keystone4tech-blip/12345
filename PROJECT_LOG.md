# Журнал проекта (PROJECT_LOG.md)

## Дата: 2026-04-08 (Исправление критической ошибки запуска)
### Изменения:
- **Hotfix (TelegramBadRequest)**:
  - `bot/app/utils/premium_emojis.py`: Усилена валидация в Middleware. Теперь бот проверяет не только автоматически подставляемые ID, но и те, что были установлены вручную (например, в стилевых настройках Mini App). Любой нечисловой ID теперь принудительно сбрасывается, предотвращая критическую ошибку API.
- **Hotfix (UnboundLocalError)**:
  - `bot/app/handlers/start.py`: Исправлена критическая ошибка в команде `/start`, вызванная перекрытием глобальной переменной `get_texts` локальным импортом.
- **UX (Premium Emojis)**:
  - `bot/app/handlers/admin/bot_configuration.py`: Реализован полностью бесшовный возврат к сетке эмодзи после удаления привязки или обновления ID (через редактирование существующего сообщения).
- **New Feature (Premium Emojis)**:
  - `bot/app/handlers/admin/bot_configuration.py`: Добавлена кнопка «Изменить» для существующих привязок эмодзи, позволяющая быстро обновить Premium ID без удаления старой записи.
- **Hotfix (ValidationError)**:
  - `bot/app/handlers/admin/bot_configuration.py`: Исправлена ошибка `Instance is frozen`, возникавшая при попытке изменить `callback.data` напрямую. Теперь `show_premium_emojis_menu` поддерживает явную передачу номера страницы.
- **Hotfix (SyntaxError)**:
  - `bot/app/handlers/admin/bot_configuration.py`: Исправлен `SyntaxError` (отсутствующий блок `except` у `try`), предотвращавший запуск бота. Добавлена корректная обработка ошибок парсинга значений.

## Дата: 2026-04-08 (Финальная стадия миграции Rich Text)
### Изменения:
- **Rich Text & Premium Emoji Migration (Завершено)**:
  - `bot/app/handlers/admin/tariffs.py`: Внедрена поддержка `html_text` и валидация HTML для тарифов.
  - `bot/app/handlers/admin/servers.py`: Внедрена поддержка `html_text` и валидация HTML для серверов.
  - `bot/app/handlers/admin/messages.py`: Валидация HTML для рассылок, `strip_html` для кнопок.
  - `bot/app/handlers/admin/promo_offers.py`: Внедрена поддержка `html_text`, валидация HTML и очистка кнопок (`strip_html`).
  - `bot/app/handlers/admin/polls.py`: Поддержка `html_text` для всех полей, полная валидация HTML-тегов, удаление избыточного экранирования в превью.
  - `bot/app/handlers/admin/faq.py`, `welcome_text.py`, `rules.py`, `privacy_policy.py`, `public_offer.py`, `user_messages.py`: Проверена и подтверждена работа валидации HTML и поддержки Rich Text.
  - **Premium Emojis Update**: Расширен список `BASE_EMOJIS` в `bot/app/utils/premium_emojis.py`. Добавлен эмодзи «🎫» (Промокод) и другие недостающие иконки из локализации, что позволяет настраивать их Premium-версии в админ-панели.
  - **CI/CD Update**: Автоматический деплой временно отключен (триггер `push` заменен на `workflow_dispatch`), чтобы избежать ошибок сборки, пока бот не развернут на сервере.

- **Оптимизация админ-панели (UX/UI)**:
    - `bot/app/utils/validators.py`: Справка по HTML сокращена до одной лаконичной строки.
    - `bot/app/handlers/admin/user_messages.py`: Промпты ввода текста стали максимально простыми («Просто отправьте текст...»).
    - `bot/app/handlers/admin/welcome_text.py` & `messages.py`: Исправлен превью (замена `code` на `blockquote`).
- **Система Auto-Sync**:
    - Внедрена автоматическая синхронизация схемы БД при запуске (`app/database/schema_sync.py`).

### Структура:
- `bot/app/database/schema_sync.py` [NEW] — авто-восстановление БД.
- `bot/app/handlers/admin/user_messages.py` [MODIFY] — чистые списки и живой превью.
- `bot/app/handlers/admin/welcome_text.py` [MODIFY] — живой превью приветствия.
- `bot/app/handlers/admin/messages.py` [MODIFY] — живой превью закрепа.

### Структура:
- `bot/migrations/alembic/versions/0017_add_buttons_to_broadcast_history.py` [RENAMED/NEW]
- `bot/migrations/alembic/versions/0018_add_buttons_to_pinned_messages.py` [RENAMED/NEW]
- `bot/app/services/pinned_message_service.py` [MODIFY]
- `bot/app/handlers/admin/messages.py` [MODIFY]

### Заметки:
- Для правильной работы кнопок в закрепе необходимо применить миграцию БД.

## Дата: 2026-04-08 (Расширение конструктора кнопок: Эмодзи и Порядок)
### Изменения:
- **Advanced Button Configuration**:
  - `bot/app/states.py`: Добавлено состояние `waiting_for_broadcast_button_emoji`.
  - `bot/app/keyboards/admin.py`: 
    - Кнопка создания теперь имеет иконку: `➕ Создать свою кнопку`.
    - Кастомные кнопки в селекторе теперь отображаются со своими реальными цветами (стилями).
    - Добавлена клавиатура `get_broadcast_button_emoji_keyboard` для пропуска шага с эмодзи.
  - `bot/app/handlers/admin/messages.py`:
    - **Порядок**: В функции `create_broadcast_keyboard` кастомные кнопки перемещены в самое начало (над стандартными).
    - **Новый шаг**: После выбора цвета добавлен обязательный этап запроса эмодзи.
    - Реализованы обработчики `process_custom_button_emoji` и `process_custom_button_emoji_skip`.
    - Эмодзи автоматически добавляется в начало текста кнопки с пробелом: `{emoji} {text}`.

### Заметки:
- **Обычная кнопка**: Если выбран стиль «Обычная», в объект `InlineKeyboardButton` не передается параметр `style`, что делает её стандартной.
- **Порядок**: Список кастомных кнопок отображается в порядке их создания над кнопкой создания новой.

## Дата: 2026-04-08 (Интеграция интерфейса Системы Подарков)
### Изменения:
- **Gift System Configuration (Backend & UI)**:
  - `bot/app/config.py`: Добавлены переменные конфигурирования: `GIFTS_ENABLED`, `GIFTS_BUTTON_VISIBLE`, `GIFTS_BUTTON_STYLE`, `GIFTS_BUTTON_EMOJI`, `GIFTS_SHARE_MESSAGE_TEMPLATE`.
  - `bot/app/services/system_settings_service.py`:
    - Регистрация новой категории `GIFTS` («🎁 Система подарков»).
    - Настройка подсказок (hints) для каждого параметра с примерами и предупреждениями.
    - Добавлены варианты выбора стиля кнопки (choices) для `GIFTS_BUTTON_STYLE`.
    - Настроен маппинг префиксов `GIFTS_` для автоматической привязки настроек к категории.
  - `bot/app/handlers/admin/bot_configuration.py`: 
    - В метаданные `CATEGORY_GROUP_METADATA` добавлена группа `gifts` с поддержкой живого отображения статуса (включена/выключена).
    - Раздел «Система подарков» интегрирован в общий порядок отображения настроек в админке.

### Структура:
- `bot/app/config.py` [MODIFY] — новые настройки в Settings.
- `bot/app/services/system_settings_service.py` [MODIFY] — бизнес-логика регистрации категорий.
- `bot/app/handlers/admin/bot_configuration.py` [MODIFY] — интерфейс панели управления.

## Дата: 2026-04-08
### Изменения:
- **Исправление ошибок**:
    - Устранена ошибка `TelegramBadRequest`, связанная с неверным типом поля `icon_custom_emoji_id` в кнопках главного меню.
    - Изменен тип настройки `GIFTS_BUTTON_EMOJI` в `config.py` на `int | None`.
    - Улучшена логика формирования кнопок в `inline.py` (теперь поле передается только при наличии значения).
    - Исправлен маппинг категорий в `system_settings_service.py` для корректного отображения настроек системы подарков в админ-панели.
- **Реорганизация интерфейса**:
    - Кнопка «Язык» удалена из главного меню и перенесена в команду `/language`.
    - Добавлена динамическая кнопка «Подарить VPN» в главное меню.
### Структура:
- `/app/handlers/menu.py` (добавлен `/language`)
- `/app/keyboards/inline.py` (обновлено главное меню)
- `/app/services/system_settings_service.py` (новые метаданные)
- `/app/config.py` (новые параметры GIFTS_*)
### Заметки:
- Ожидается перенос кода системы подарков из `merged_project` (модели, сервисы, хендлеры).
- Ошибка `TelegramNetworkError` в логах носит внешний характер (проблемы со связью на сервере).

## Дата: 2026-04-08 (Реорганизация меню: Язык -> Подарки)
### Изменения:
- **Menu Reorganization & Command Integration**:
  - `bot/app/config.py`: Добавлена настройка `GIFTS_BUTTON_TEXT` для кастомизации названия кнопки подарков.
  - `bot/app/services/system_settings_service.py`: Регистрация подсказки для новой настройки текста кнопки.
  - `bot/app/utils/bot_commands.py`: В меню команд Telegram (синяя кнопка «Меню») добавлена команда `/language` («🌐 Сменить язык»).
  - `bot/app/handlers/menu.py`: Реализован обработчик `cmd_language` для вызова меню выбора языка по команде.
  - `bot/app/keyboards/inline.py`: 
    - Удалена кнопка выбора языка из функций главного меню (`get_main_menu_keyboard` и `_build_cabinet_main_menu_keyboard`).
    - На её место добавлена кнопка подарков, которая отображается динамически при включенном `GIFTS_ENABLED`. Поддерживает кастомный текст, стили и премиум-эмодзи.

### Структура:
- `bot/app/handlers/menu.py` [MODIFY] — новый обработчик `/language`.
- `bot/app/keyboards/inline.py` [MODIFY] — обновленное главное меню.

## Дата: 2026-04-08 (Полная реализация Системы Подарков)
### Изменения:
- **Core Logic & Database**:
  - `bot/app/database/models.py`: Добавлена модель `Gift` и тип транзакции `GIFT_VPN`.
  - `bot/app/services/gift_service.py`: Создан сервисный слой для управления подарками (создание, получение, активация).
- **User Interface (Handlers)**:
  - `bot/app/handlers/gift_vpn.py`: Реализован полный цикл покупки и управления подарками (выбор тарифа -> оплата -> ссылка -> история).
  - `bot/app/handlers/start.py`: Интегрирована поддержка диплинков `gift_`. Система теперь автоматически предлагает активировать подарок при входе по ссылке.
- **Localization**:
  - `bot/locales/ru.json`: Добавлены все необходимые ключи для системы подарков.
- **Integration**:
  - `bot/app/bot.py`: Новые хендлеры зарегистрированы в диспетчере.

### Структура:
- `bot/app/database/models.py` [MODIFY] — модель Gift.
- `bot/app/services/gift_service.py` [NEW] — логика активации.
- `bot/app/handlers/gift_vpn.py` [NEW] — UI покупки подарка.
- `bot/app/handlers/start.py` [MODIFY] — поддержка активации через /start.

## Дата: 2026-04-08 (Рефакторинг и исправления Premium-эмодзи)
### Изменения:
- **Централизация логики**: Создана универсальная функция `get_custom_emoji_id` в `app/utils/premium_emojis.py`.
- **Рефакторинг админки**: 
    - Обработчик `handle_edit_setting` в `bot_configuration.py` теперь автоматически извлекает ID из присланных премиум-эмодзи для настроек типа EMOJI/ICON.
    - Обработчик кнопок рассылок в `messages.py` переведен на использование общей функции.
- **Исправление ошибок**:
    - В `bot/app/handlers/admin/bot_configuration.py` исправлена синтаксическая ошибка с отступами.
    - В `bot/app/keyboards/inline.py` улучшен визуал кнопки подарков: стандартный эмодзи 🎁 автоматически удаляется из текста, если задан кастомный ID, чтобы избежать дублирования.
- **Поддержка API**: ID премиум-эмодзи теперь всегда передаются как строки для максимальной совместимости.

### Структура:
- `bot/app/utils/premium_emojis.py` [MODIFY] — новые утилиты.
- `bot/app/handlers/admin/bot_configuration.py` [MODIFY] — обновление и фикс.
- `bot/app/handlers/admin/messages.py` [MODIFY] — рефакторинг хендлеров.

### Заметки:
- Теперь администратору достаточно отправить сам премиум-эмодзи в настройку, чтобы бот подхватил его ID.
- Система подарков полностью функциональна и поддерживает кастомные иконки.
