# 🚀 Инструкция по деплою MozhnoVPN

## Содержание

1. [Архитектура проекта](#архитектура-проекта)
2. [Подготовка сервера](#подготовка-сервера)
3. [Настройка .env файлов](#настройка-env-файлов)
4. [Первый запуск](#первый-запуск)
5. [Настройка автодеплоя (GitHub Actions)](#настройка-автодеплоя)
6. [Обновление проекта](#обновление-проекта)
7. [Мониторинг и логи](#мониторинг-и-логи)
8. [Откат при ошибках](#откат-при-ошибках)
9. [FAQ и решение проблем](#faq-и-решение-проблем)

---

## Архитектура проекта

```
┌─────────────────────────────────────────────┐
│                  СЕРВЕР                      │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ PostgreSQL│  │  Redis   │  │  Cabinet  │  │
│  │  :5432    │  │  :6379   │  │  :3020    │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  │
│       │              │              │        │
│       └──────┬───────┘              │        │
│              │                      │        │
│         ┌────┴──────┐               │        │
│         │   BOT     ├───────────────┘        │
│         │  :8080    │  (API для кабинета)     │
│         └───────────┘                        │
│                                              │
└──────────────────────────────────────────────┘
         │
         │ API запросы
         ▼
┌─────────────────┐
│ Remnawave Panel │
│ p.mozhnovpn.tech│
└─────────────────┘
```

### Компоненты

| Сервис | Описание | Порт | Технология |
|--------|----------|------|------------|
| `bot` | Telegram бот | 8080 | Python 3.13 |
| `cabinet` | Веб-кабинет | 3020 | Vite/React + nginx |
| `postgres` | База данных | 5432 (внутренний) | PostgreSQL 15 |
| `redis` | Кеш и очереди | 6379 (внутренний) | Redis 7 |

---

## Подготовка сервера

### Автоматическая настройка (рекомендуется)

Подключитесь к серверу по SSH и выполните:

```bash
# Скачиваем и запускаем скрипт настройки
curl -sSL https://raw.githubusercontent.com/keystone4tech-blip/12345/main/scripts/server-setup.sh -o setup.sh
chmod +x setup.sh
sudo bash setup.sh
```

Скрипт автоматически:
- Обновит систему
- Установит Docker и Docker Compose
- Настроит файрвол (UFW)
- Клонирует репозиторий в `/opt/mozhnovpn`
- Создаст .env файлы из шаблонов

### Ручная настройка

Если предпочитаете настроить вручную:

```bash
# 1. Обновление системы
sudo apt update && sudo apt upgrade -y

# 2. Установка Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker

# 3. Установка Git
sudo apt install -y git

# 4. Клонирование репозитория
git clone https://github.com/keystone4tech-blip/12345.git /opt/mozhnovpn
cd /opt/mozhnovpn

# 5. Создание .env файлов
cp .env.example .env
cp bot/.env.example bot/.env
cp cabinet/.env.example cabinet/.env
```

---

## Настройка .env файлов

### Корневой `.env`

Файл: `/opt/mozhnovpn/.env`

```ini
# База данных
POSTGRES_DB=jarvis_vpn
POSTGRES_USER=postgres
POSTGRES_PASSWORD=ваш_надёжный_пароль

# Порты
BOT_API_PORT=8080
CABINET_PORT=3020

# Кабинет
VITE_API_URL=http://bot:8080/cabinet
VITE_TELEGRAM_BOT_USERNAME=Jarvis_VPN_Robot
VITE_APP_NAME=Jarvis VPN Cabinet
VITE_APP_LOGO=MV
```

### Бот `bot/.env`

Файл: `/opt/mozhnovpn/bot/.env`

> **Важно**: Скопируйте ваш текущий `bot/.env` с рабочей машины на сервер. Он содержит API ключи и токены.

Ключевые переменные:
```ini
BOT_TOKEN=ваш_токен_бота
ADMIN_IDS=ваш_telegram_id
REMNAWAVE_API_URL=https://p.mozhnovpn.tech/
REMNAWAVE_API_KEY=ваш_api_ключ
```

### Кабинет `cabinet/.env`

Файл: `/opt/mozhnovpn/cabinet/.env`

```ini
VITE_API_URL=http://bot:8080/cabinet
VITE_TELEGRAM_BOT_USERNAME=Jarvis_VPN_Robot
VITE_APP_NAME=Jarvis VPN Cabinet
VITE_APP_LOGO=MV
CABINET_PORT=3020
```

---

## Первый запуск

```bash
# Переходим в директорию проекта
cd /opt/mozhnovpn

# Собираем и запускаем все сервисы
docker compose up -d --build

# Проверяем статус
docker compose ps

# Смотрим логи (все сервисы)
docker compose logs -f

# Смотрим логи бота
docker compose logs -f bot

# Смотрим логи кабинета
docker compose logs -f cabinet
```

### Проверка работоспособности

```bash
# Бот API
curl http://localhost:8080/health

# Кабинет
curl http://localhost:3020/
```

---

## Настройка автодеплоя

### Шаг 1: Генерация SSH-ключа

На **сервере** (если ещё нет ключа):

```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Скопируйте **приватный** ключ:
```bash
cat ~/.ssh/github_deploy
```

### Шаг 2: Настройка GitHub Secrets

Перейдите в репозиторий GitHub:
**Settings → Secrets and variables → Actions → New repository secret**

Создайте следующие секреты:

| Имя секрета | Значение |
|------------|----------|
| `SERVER_HOST` | IP адрес вашего сервера |
| `SERVER_USER` | `root` |
| `SSH_PRIVATE_KEY` | Содержимое приватного ключа (`~/.ssh/github_deploy`) |
| `PROJECT_PATH` | `/opt/mozhnovpn` |

### Шаг 3: Проверка

1. Сделайте любое изменение в файлах `bot/` или `cabinet/`
2. Закоммитьте и отправьте в `main`:
   ```bash
   git add .
   git commit -m "test: проверка автодеплоя"
   git push origin main
   ```
3. Перейдите на GitHub → **Actions** и убедитесь, что workflow запустился
4. Проверьте на сервере: `docker compose ps`

---

## Обновление проекта

### Автоматическое (рекомендуется)

Просто сделайте push в ветку `main`:
```bash
git add .
git commit -m "описание изменений"
git push origin main
```

GitHub Actions автоматически:
1. Подключится к серверу по SSH
2. Скачает обновления (`git pull`)
3. Пересоберёт изменённые контейнеры
4. Перезапустит сервисы

### Ручное обновление

На сервере:
```bash
cd /opt/mozhnovpn
bash scripts/deploy.sh
```

---

## Мониторинг и логи

```bash
# Статус всех контейнеров
docker compose ps

# Логи всех сервисов (в реальном времени)
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f bot
docker compose logs -f cabinet
docker compose logs -f postgres
docker compose logs -f redis

# Последние 100 строк логов бота
docker compose logs --tail=100 bot

# Использование ресурсов
docker stats

# Место на диске
docker system df
```

---

## Откат при ошибках

### Откат на предыдущий коммит

```bash
cd /opt/mozhnovpn

# Смотрим историю коммитов
git log --oneline -10

# Откатываемся на нужный коммит
git reset --hard <commit_hash>

# Пересобираем и запускаем
docker compose up -d --build
```

### Перезапуск одного сервиса

```bash
# Перезапуск только бота
docker compose restart bot

# Полная пересборка бота
docker compose up -d --build bot
```

### Полный сброс

```bash
cd /opt/mozhnovpn

# Остановка всех контейнеров
docker compose down

# Удаление образов (НЕ данных!)
docker compose down --rmi local

# Полная пересборка с нуля
docker compose up -d --build
```

> ⚠️ **Внимание**: `docker compose down -v` удалит тома (БД и Redis)! Используйте только если хотите полный сброс данных.

---

## FAQ и решение проблем

### Контейнер не стартует

```bash
# Проверьте логи
docker compose logs bot

# Проверьте .env файл
cat bot/.env

# Проверьте что порт не занят
ss -tlnp | grep 8080
```

### Нет подключения к Remnawave API

Убедитесь что:
1. `REMNAWAVE_API_URL` в `bot/.env` корректный
2. На сервере панели nginx проксирует `/api/` на бэкенд (порт 3000)
3. API ключ валидный

### Как добавить SSL (HTTPS)?

Рекомендуется использовать **Nginx Proxy Manager** или **Caddy**:

```bash
# Установка Nginx Proxy Manager (рядом с проектом)
docker run -d \
  --name nginx-proxy \
  -p 80:80 -p 443:443 -p 81:81 \
  --network app_network \
  jc21/nginx-proxy-manager:latest
```

Затем в веб-интерфейсе (порт 81) настройте проксирование:
- `cabinet.yourdomain.com` → `cabinet:80`
- `api.yourdomain.com` → `bot:8080`

### Как посмотреть размер данных?

```bash
docker system df            # Общая статистика Docker
du -sh /opt/mozhnovpn/      # Размер проекта
docker volume ls             # Список томов
```
