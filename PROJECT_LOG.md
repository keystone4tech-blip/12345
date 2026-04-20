# PROJECT_LOG.md

## Дата: 2026-04-20 (обновление 3)
### Изменения:
- Реализована автоматизация развёртывания (CI/CD) через GitHub Actions.
- Все ключи и `.env` файлы безопасно перенесены на production сервер.
- Исправлена критическая ошибка миграции (`DuplicateColumnError`) в таблице `broadcast_history` (миграция 0017 пропатчена и загружена на GitHub).
- Настроен `Nginx` Reverse Proxy для кабинета на сервере (31.13.208.149).
- SSL сертификат получен через `certbot` для домена `lk.mozhnovpn.tech` и настроено его автообновление (cron/systemd).
- В `bot/.env` добавлен `CABINET_ALLOWED_ORIGINS=https://lk.mozhnovpn.tech` для работы CORS.

### Заметки:
- Для исправления ошибки 404 API ключа Remnawave необходимо настроить Nginx на *сервере самой панели* (`p.mozhnovpn.tech`, IP `144.31.166.158`), так как он не проксирует запросы `/api/` на бэкенд порт панели.

## Дата: 2026-04-20 (обновление 2)
### Изменения:
- Создана полная инфраструктура для деплоя проекта на сервер
- Создан единый `docker-compose.yml` в корне проекта (оркестратор всех сервисов)
- Создан `scripts/server-setup.sh` — скрипт первоначальной настройки Ubuntu сервера
- Создан `scripts/deploy.sh` — скрипт деплоя с автооткатом при ошибках
- Обновлён `.github/workflows/deploy.yml` — CI/CD с автодеплоем при push в main
- Создан `.env.example` — шаблон переменных окружения
- Создан `DEPLOY.md` — полная инструкция по деплою
- Создан корневой `.gitignore`

### Структура проекта:
```
/проект
  /bot                          # Telegram бот (Python)
    /app                        # Исходный код бота
      /external                 # API клиенты (remnawave_api.py)
      /handlers                 # Обработчики команд
      /services                 # Бизнес-логика
      /keyboards                # Клавиатуры бота
      /config.py                # Конфигурация Pydantic
    /data                       # Данные и бэкапы
    /logs                       # Логи бота
    /locales                    # Локализация
    main.py                     # Точка входа бота
    Dockerfile                  # Docker-образ бота
    docker-compose.yml          # Docker Compose (для отдельного запуска)
    docker-compose.local.yml    # Docker Compose (локальная разработка)
    .env                        # Переменные окружения бота (НЕ в git)
    .env.example                # Шаблон переменных
  /cabinet                      # Веб-кабинет (Vite/React/TypeScript)
    /src                        # Исходный код фронтенда
    /public                     # Статические файлы
    Dockerfile                  # Docker-образ кабинета
    docker-compose.yml          # Docker Compose (для отдельного запуска)
    nginx.conf                  # Конфиг nginx для SPA
    .env                        # Переменные окружения (НЕ в git)
    .env.example                # Шаблон переменных
  /scripts                      # Скрипты деплоя
    server-setup.sh             # Настройка чистого сервера
    deploy.sh                   # Скрипт обновления на сервере
  /.github/workflows
    deploy.yml                  # GitHub Actions CI/CD
  docker-compose.yml            # ГЛАВНЫЙ: единый docker-compose для сервера
  .env.example                  # Шаблон переменных (корневой)
  .gitignore                    # Git-исключения
  DEPLOY.md                     # Инструкция по деплою
  PROJECT_LOG.md                # Этот файл
```

### CI/CD пайплайн:
```
Git Push (main) → GitHub Actions → SSH на сервер → git pull → docker compose build → docker compose up -d
```

### Заметки:
- Панель Remnawave (`p.mozhnovpn.tech`) — на отдельном сервере
- Ошибка 404 API `/api/system/stats` — проблема nginx на сервере панели (не проксирует /api/ на бэкенд порт 3000)
- Бот работает в режиме polling (вебхуки отключены)
- Для production рекомендуется настроить SSL через Nginx Proxy Manager или Caddy

## Дата: 2026-04-20 (обновление 1)
### Изменения:
- Бот переведен в режим **polling** из-за проблем с DNS для вебхука
- Закомментирован `REMNAWAVE_AUTH_TYPE=bearer` в `.env`
- Выполнен перезапуск Docker-контейнеров

### Заметки:
- Вебхуки временно отключены до исправления проблем с DNS
- По-прежнему сохраняется ошибка **404** при подключении к API панели (`/api/system/stats`)
