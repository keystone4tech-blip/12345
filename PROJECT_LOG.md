# Журнал проекта (PROJECT_LOG.md)

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

### Актуальная структура проекта:
- `/bot/app/handlers/admin`: Все модули управления контентом поддерживают нативный HTML Telegram.
- `/bot/app/utils/validators.py`: Централизованные утилиты `validate_html_tags` и `strip_html`.

### Заметки:
- **Критическое правило**: Тело сообщения = `message.html_text` + `validate_html_tags`.
- **Критическое правило**: Текст кнопки = `strip_html(message.text)`.
- **Эмодзи**: Premium-эмодзи поддерживаются автоматически через `html_text`.
- **Валидация**: Перед сохранением в БД всегда вызывать `validate_html_tags`, чтобы избежать сбоев при отправке сообщений.

