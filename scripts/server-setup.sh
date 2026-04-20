#!/bin/bash
# ==============================================================
# СКРИПТ ПЕРВОНАЧАЛЬНОЙ НАСТРОЙКИ СЕРВЕРА
# ==============================================================
# Запускать на чистом Ubuntu сервере:
#   curl -sSL https://raw.githubusercontent.com/keystone4tech-blip/12345/main/scripts/server-setup.sh | bash
# ИЛИ:
#   chmod +x server-setup.sh && ./server-setup.sh
# ==============================================================

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Без цвета

# Логирование
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}==== $1 ====${NC}"; }

# Проверяем что скрипт запущен от root
if [ "$EUID" -ne 0 ]; then
    log_error "Запустите скрипт от root: sudo bash server-setup.sh"
    exit 1
fi

# ============================================
# Переменные (можно менять)
# ============================================
REPO_URL="https://github.com/keystone4tech-blip/12345.git"  # URL репозитория
PROJECT_DIR="/opt/mozhnovpn"  # Директория проекта на сервере
BRANCH="main"  # Ветка для клонирования

# ============================================
# Шаг 1: Обновление системы
# ============================================
log_step "Шаг 1: Обновление системы"
apt-get update -y && apt-get upgrade -y
log_info "Система обновлена"

# ============================================
# Шаг 2: Установка необходимых пакетов
# ============================================
log_step "Шаг 2: Установка необходимых пакетов"
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    ufw \
    fail2ban \
    htop \
    wget \
    unzip
log_info "Пакеты установлены"

# ============================================
# Шаг 3: Установка Docker
# ============================================
log_step "Шаг 3: Установка Docker"

# Проверяем, не установлен ли Docker уже
if command -v docker &> /dev/null; then
    log_warn "Docker уже установлен: $(docker --version)"
else
    # Добавляем GPG ключ Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    # Добавляем репозиторий Docker
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Устанавливаем Docker
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Запускаем Docker и добавляем в автозагрузку
    systemctl start docker
    systemctl enable docker

    log_info "Docker установлен: $(docker --version)"
    log_info "Docker Compose: $(docker compose version)"
fi

# ============================================
# Шаг 4: Настройка файрвола
# ============================================
log_step "Шаг 4: Настройка файрвола (UFW)"

ufw default deny incoming    # Запретить все входящие
ufw default allow outgoing   # Разрешить все исходящие
ufw allow 22/tcp             # SSH
ufw allow 80/tcp             # HTTP
ufw allow 443/tcp            # HTTPS
ufw allow 8080/tcp           # Bot API
ufw allow 3020/tcp           # Cabinet

# Включаем файрвол (без подтверждения)
echo "y" | ufw enable
log_info "Файрвол настроен"

# ============================================
# Шаг 5: Клонирование репозитория
# ============================================
log_step "Шаг 5: Клонирование репозитория"

if [ -d "$PROJECT_DIR" ]; then
    log_warn "Директория $PROJECT_DIR уже существует"
    log_info "Обновляем репозиторий..."
    cd "$PROJECT_DIR"
    git pull origin "$BRANCH"
else
    log_info "Клонируем репозиторий в $PROJECT_DIR..."
    git clone -b "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

log_info "Репозиторий готов: $PROJECT_DIR"

# ============================================
# Шаг 6: Создание .env файлов
# ============================================
log_step "Шаг 6: Настройка .env файлов"

# Корневой .env (для docker-compose.yml)
if [ ! -f "$PROJECT_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        log_info "Создан .env из .env.example"
    else
        log_warn "Файл .env.example не найден, создайте .env вручную"
    fi
else
    log_warn ".env уже существует, пропускаем"
fi

# .env бота
if [ ! -f "$PROJECT_DIR/bot/.env" ]; then
    if [ -f "$PROJECT_DIR/bot/.env.example" ]; then
        cp "$PROJECT_DIR/bot/.env.example" "$PROJECT_DIR/bot/.env"
        log_info "Создан bot/.env из bot/.env.example"
    else
        log_warn "bot/.env.example не найден"
    fi
else
    log_warn "bot/.env уже существует, пропускаем"
fi

# .env кабинета
if [ ! -f "$PROJECT_DIR/cabinet/.env" ]; then
    if [ -f "$PROJECT_DIR/cabinet/.env.example" ]; then
        cp "$PROJECT_DIR/cabinet/.env.example" "$PROJECT_DIR/cabinet/.env"
        log_info "Создан cabinet/.env из cabinet/.env.example"
    else
        log_warn "cabinet/.env.example не найден"
    fi
else
    log_warn "cabinet/.env уже существует, пропускаем"
fi

# ============================================
# Шаг 7: Создание директорий для данных
# ============================================
log_step "Шаг 7: Создание директорий"

mkdir -p "$PROJECT_DIR/bot/logs"
mkdir -p "$PROJECT_DIR/bot/data"
mkdir -p "$PROJECT_DIR/logs"

log_info "Директории созданы"

# ============================================
# Шаг 8: Делаем скрипт деплоя исполняемым
# ============================================
log_step "Шаг 8: Подготовка скриптов"

chmod +x "$PROJECT_DIR/scripts/deploy.sh" 2>/dev/null || true
chmod +x "$PROJECT_DIR/scripts/server-setup.sh" 2>/dev/null || true

log_info "Скрипты готовы к запуску"

# ============================================
# Финальные инструкции
# ============================================
echo ""
echo "============================================================"
echo -e "${GREEN}✅ СЕРВЕР НАСТРОЕН УСПЕШНО!${NC}"
echo "============================================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "  1. Отредактируйте .env файлы:"
echo "     nano $PROJECT_DIR/.env"
echo "     nano $PROJECT_DIR/bot/.env"
echo "     nano $PROJECT_DIR/cabinet/.env"
echo ""
echo "  2. Запустите проект:"
echo "     cd $PROJECT_DIR"
echo "     docker compose up -d --build"
echo ""
echo "  3. Проверьте статус:"
echo "     docker compose ps"
echo "     docker compose logs -f"
echo ""
echo "  4. Настройте GitHub Secrets для автодеплоя:"
echo "     - SERVER_HOST: IP вашего сервера"
echo "     - SERVER_USER: root"
echo "     - SSH_PRIVATE_KEY: ваш приватный SSH ключ"
echo "     - PROJECT_PATH: $PROJECT_DIR"
echo ""
echo "============================================================"
