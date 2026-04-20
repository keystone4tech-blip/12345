#!/bin/bash
# ==============================================================
# СКРИПТ ДЕПЛОЯ (выполняется на сервере)
# ==============================================================
# Вызывается из GitHub Actions или вручную:
#   cd /opt/mozhnovpn && bash scripts/deploy.sh
# ==============================================================

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Логирование с временными метками
log_info()  { echo -e "$(date '+%Y-%m-%d %H:%M:%S') ${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "$(date '+%Y-%m-%d %H:%M:%S') ${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "$(date '+%Y-%m-%d %H:%M:%S') ${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n$(date '+%Y-%m-%d %H:%M:%S') ${BLUE}==== $1 ====${NC}"; }

# Директория проекта
PROJECT_DIR="${PROJECT_PATH:-/opt/mozhnovpn}"
BRANCH="${DEPLOY_BRANCH:-main}"
LOG_FILE="$PROJECT_DIR/logs/deploy.log"

# Создаём директорию для логов деплоя
mkdir -p "$PROJECT_DIR/logs"

# Логируем всё в файл и в консоль
exec > >(tee -a "$LOG_FILE") 2>&1

log_step "Начало деплоя"
log_info "Директория: $PROJECT_DIR"
log_info "Ветка: $BRANCH"

# ============================================
# Шаг 1: Переход в директорию проекта
# ============================================
cd "$PROJECT_DIR" || {
    log_error "Директория $PROJECT_DIR не найдена!"
    exit 1
}

# ============================================
# Шаг 2: Получение обновлений из Git
# ============================================
log_step "Получение обновлений из Git"

# Сохраняем текущий коммит для возможного отката
PREV_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
log_info "Текущий коммит: $PREV_COMMIT"

# Получаем обновления
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

NEW_COMMIT=$(git rev-parse HEAD)
log_info "Новый коммит: $NEW_COMMIT"

# Если коммиты совпадают — нет изменений
if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
    log_warn "Нет новых изменений, пересобираем на всякий случай"
fi

# ============================================
# Шаг 3: Полная очистка старых контейнеров и кэша
# ============================================
log_step "Очистка контейнеров приложения и кэша"

# Останавливаем только приложение (БД и Redis продолжают работать)
docker compose stop bot cabinet 2>/dev/null || true
docker compose rm -f bot cabinet 2>/dev/null || true

# Полностью очищаем кэш сборщика Docker (предотвращает зависание старых файлов)
log_info "Удаление кэша сборки (builder cache)..."
docker builder prune -a -f || true

# Очистка неиспользуемых образов (освобождение места перед сборкой)
docker image prune -a -f --filter "until=24h" || true

# ============================================
# Шаг 4: Чистая пересборка и запуск
# ============================================
log_step "Чистая пересборка (--no-cache) и запуск"

# Собираем заново полностью на чистую
docker compose build --no-cache --pull bot cabinet 2>&1 || {
    log_error "Ошибка сборки! Откатываем..."
    git reset --hard "$PREV_COMMIT"
    docker compose up -d
    exit 1
}

docker compose up -d --remove-orphans 2>&1 || {
    log_error "Ошибка запуска контейнеров!"
    exit 1
}

# ============================================
# Шаг 5: Ожидание healthcheck
# ============================================
log_step "Проверка здоровья сервисов"

# Ждём 30 секунд и проверяем статус
sleep 15

# Проверяем здоровье всех контейнеров
UNHEALTHY=$(docker compose ps --format json 2>/dev/null | grep -c '"unhealthy"' || true)
if [ "$UNHEALTHY" -gt 0 ]; then
    log_warn "Есть нездоровые контейнеры ($UNHEALTHY):"
    docker compose ps
    log_warn "Проверьте логи: docker compose logs"
else
    log_info "Все контейнеры здоровы"
fi

# Показываем статус
docker compose ps

# ============================================
# Шаг 6: Очистка старых образов
# ============================================
log_step "Очистка старых образов"

# Удаляем неиспользуемые образы (освобождаем место)
docker image prune -f 2>/dev/null || true
log_info "Старые образы удалены"

# ============================================
# Завершение
# ============================================
echo ""
log_info "============================================================"
log_info "✅ Деплой завершён!"
log_info "   Коммит: $NEW_COMMIT"
log_info "   Дата:   $(date '+%Y-%m-%d %H:%M:%S')"
log_info "============================================================"
