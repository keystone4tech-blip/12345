import datetime

log_entry = """## Дата: {date} (Внедрение системы Traffic Help)

### Изменения:
- **Добавлено поле setup_help_sent в таблицу users** (`bot/app/database/models.py`, `bot/migrations/alembic/versions/c05ccd58e542_add_setup_help_sent_to_users.py`).
- **Добавлены настройки TRAFFIC_HELP_* в конфигурацию бота** (`bot/app/config.py`).
- **Создан фоновый сервис TrafficHelpService для рассылки уведомлений неактивным пользователям с подпиской** (`bot/app/services/traffic_help_service.py`).
- **Добавлен раздел админ-панели "Помощь с настройкой"** (`bot/app/keyboards/admin.py`, `bot/app/handlers/admin/admin_traffic_help.py`).
- **Сервис интегрирован в стартовую загрузку бота** (`bot/main.py`, `bot/app/bot.py`, `bot/app/handlers/admin/__init__.py`).

### Затронутые файлы:
- `bot/app/database/models.py` — [MODIFY] добавление поля `setup_help_sent`
- `bot/migrations/alembic/versions/c05ccd58e542_add_setup_help_sent_to_users.py` — [NEW] миграция
- `bot/app/config.py` — [MODIFY] настройки сервиса
- `bot/app/services/traffic_help_service.py` — [NEW] логика рассылки
- `bot/app/keyboards/admin.py` — [MODIFY] клавиатура админки
- `bot/app/handlers/admin/admin_traffic_help.py` — [NEW] хэндлеры админки
- `bot/app/bot.py` — [MODIFY] регистрация роутера
- `bot/app/handlers/admin/__init__.py` — [MODIFY] экспорт
- `bot/main.py` — [MODIFY] запуск сервиса при старте

---

""".format(date=datetime.date.today().strftime('%Y-%m-%d'))

file_path = "PROJECT_LOG.md"

with open(file_path, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

with open(file_path, "w", encoding="utf-8") as f:
    f.write(log_entry + content)

print("PROJECT_LOG.md updated")
