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
  - `bot/app/keyboards/admin.py`: Очистка меток кнопок (`strip_html`) во всех критических UI-элементах.

### Актуальная структура проекта:
- `/bot/app/handlers/admin`: Все модули управления контентом поддерживают нативный HTML Telegram.
- `/bot/app/utils/validators.py`: Централизованные утилиты `validate_html_tags` и `strip_html`.

### Заметки:
- **Критическое правило**: Тело сообщения = `message.html_text` + `validate_html_tags`.
- **Критическое правило**: Текст кнопки = `strip_html(message.text)`.
- **Эмодзи**: Premium-эмодзи поддерживаются автоматически через `html_text`.
- **Валидация**: Перед сохранением в БД всегда вызывать `validate_html_tags`, чтобы избежать сбоев при отправке сообщений.

