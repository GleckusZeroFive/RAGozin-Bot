#!/bin/bash
# ============================================================================
# start.sh — Единый скрипт запуска RAG-DEMO-PET бота
# Запуск: ./start.sh [--prod] [--rebuild] [--logs] [--stop] [--status]
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# ── Цвета ──────────────────────────────────────────────────────────────────
GREEN='\033[32m'
RED='\033[31m'
YELLOW='\033[33m'
CYAN='\033[36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# ── Compose-команда (dev по умолчанию) ─────────────────────────────────────
DC_DEV="docker compose -f docker-compose.yml -f docker-compose.dev.yml"
DC_PROD="docker compose"
DC="$DC_DEV"  # по умолчанию dev-режим

# ── Параметры ──────────────────────────────────────────────────────────────
MODE="dev"
REBUILD=false
FOLLOW_LOGS=false
DO_STOP=false
DO_STATUS=false

for arg in "$@"; do
    case "$arg" in
        --prod)    MODE="prod"; DC="$DC_PROD" ;;
        --rebuild) REBUILD=true ;;
        --logs)    FOLLOW_LOGS=true ;;
        --stop)    DO_STOP=true ;;
        --status)  DO_STATUS=true ;;
        --help|-h)
            echo "Использование: ./start.sh [ФЛАГИ]"
            echo ""
            echo "  (без флагов)   Запуск в dev-режиме (hot-reload)"
            echo "  --prod         Production-режим (без volume mounts)"
            echo "  --rebuild      Полная пересборка образа (--build)"
            echo "  --logs         Показать логи бота после старта (Ctrl+C для выхода)"
            echo "  --stop         Остановить все сервисы"
            echo "  --status       Показать статус сервисов"
            echo ""
            exit 0
            ;;
        *) echo -e "${RED}Неизвестный флаг: $arg${RESET}"; exit 1 ;;
    esac
done

# ── Вспомогательные функции ────────────────────────────────────────────────
step_num=0

step() {
    step_num=$((step_num + 1))
    echo -e "\n${CYAN}${BOLD}[$step_num]${RESET} ${BOLD}$1${RESET}"
}

ok()   { echo -e "    ${GREEN}✓${RESET} $1"; }
warn() { echo -e "    ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "    ${RED}✗${RESET} $1"; }
info() { echo -e "    ${DIM}$1${RESET}"; }

die() {
    echo -e "\n${RED}${BOLD}FATAL:${RESET} $1"
    exit 1
}

wait_for() {
    # wait_for <описание> <макс_сек> <команда...>
    local desc="$1" max="$2"; shift 2
    local i=0
    while [ $i -lt "$max" ]; do
        if "$@" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    return 1
}

# ── Trap для Ctrl+C ───────────────────────────────────────────────────────
cleanup() {
    echo -e "\n${YELLOW}Прервано пользователем.${RESET}"
    exit 130
}
trap cleanup INT TERM

# ── Баннер ─────────────────────────────────────────────────────────────────
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD} RAG-DEMO-PET Bot Launcher${RESET}"
echo -e " ${DIM}Режим: ${MODE} | $(date '+%Y-%m-%d %H:%M:%S')${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# ══════════════════════════════════════════════════════════════════════════
# --stop: остановка всех сервисов
# ══════════════════════════════════════════════════════════════════════════
if $DO_STOP; then
    step "Остановка сервисов"

    # Останавливаем контейнеры (пробуем dev, потом prod)
    if $DC_DEV ps --quiet bot 2>/dev/null | grep -q .; then
        $DC_DEV down
        ok "Docker-контейнеры (dev) остановлены"
    elif $DC_PROD ps --quiet bot 2>/dev/null | grep -q .; then
        $DC_PROD down
        ok "Docker-контейнеры (prod) остановлены"
    else
        # Просто пробуем оба
        $DC_DEV down 2>/dev/null || $DC_PROD down 2>/dev/null || true
        ok "Docker-контейнеры остановлены"
    fi

    # Останавливаем proxy
    PROXY_PID=$(lsof -ti :8200 2>/dev/null || true)
    if [ -n "$PROXY_PID" ]; then
        kill "$PROXY_PID" 2>/dev/null || true
        ok "Claude proxy (PID $PROXY_PID) остановлен"
    else
        info "Claude proxy не был запущен"
    fi

    echo -e "\n${GREEN}${BOLD}Все сервисы остановлены.${RESET}\n"
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════
# --status: показать текущее состояние
# ══════════════════════════════════════════════════════════════════════════
if $DO_STATUS; then
    step "Статус Docker"
    if docker info >/dev/null 2>&1; then
        ok "Docker daemon запущен"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null | while read -r line; do
            info "$line"
        done
    else
        fail "Docker daemon не запущен"
    fi

    step "Статус Claude proxy"
    if curl -sf http://localhost:8200/health >/dev/null 2>&1; then
        ok "Proxy отвечает на :8200/health"
    else
        fail "Proxy не доступен"
    fi

    step "Запуск healthcheck.py"
    cd "$PROJECT_DIR"
    if [ -d ".venv" ] && [ -f ".venv/bin/python" ]; then
        .venv/bin/python healthcheck.py 2>/dev/null || true
    else
        warn "Нет .venv — healthcheck.py недоступен"
    fi
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════
# Шаг 1: Docker daemon
# ══════════════════════════════════════════════════════════════════════════
step "Docker daemon"

if docker info >/dev/null 2>&1; then
    ok "Docker daemon уже запущен"
else
    warn "Docker daemon не запущен, запускаю..."

    # Способ 1: service (стандартный)
    sudo service docker start >/dev/null 2>&1 || true

    if ! wait_for "Docker daemon (service)" 8 docker info; then
        # Способ 2: dockerd напрямую (WSL2 fallback)
        info "service docker start не сработал, пробую dockerd..."
        sudo dockerd >/dev/null 2>&1 &

        if ! wait_for "Docker daemon (dockerd)" 10 docker info; then
            die "Не удалось запустить Docker daemon.\n    Попробуйте вручную: sudo service docker start\n    или: sudo dockerd &"
        fi
    fi

    ok "Docker daemon запущен"
fi

# ══════════════════════════════════════════════════════════════════════════
# Шаг 2: Сеть rag-shared
# ══════════════════════════════════════════════════════════════════════════
step "Docker network: rag-shared"

if docker network inspect rag-shared >/dev/null 2>&1; then
    ok "Сеть rag-shared существует"
else
    docker network create rag-shared >/dev/null 2>&1
    ok "Сеть rag-shared создана"
fi

# ══════════════════════════════════════════════════════════════════════════
# Шаг 3: PostgreSQL + Qdrant
# ══════════════════════════════════════════════════════════════════════════
step "PostgreSQL + Qdrant"

# Запускаем инфраструктурные сервисы
$DC up -d postgres qdrant 2>&1 | while read -r line; do
    info "$line"
done

# Ждём healthy для PostgreSQL
info "Жду PostgreSQL healthy..."
PG_CONTAINER=$($DC ps -q postgres 2>/dev/null || echo "")
if [ -n "$PG_CONTAINER" ]; then
    if wait_for "PostgreSQL" 30 docker inspect --format='{{.State.Health.Status}}' "$PG_CONTAINER" 2>/dev/null | grep -q healthy 2>/dev/null; then
        # Проверяем ещё раз явно
        true
    fi
    PG_STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$PG_CONTAINER" 2>/dev/null || echo "unknown")
    if [ "$PG_STATUS" = "healthy" ]; then
        ok "PostgreSQL healthy"
    else
        warn "PostgreSQL статус: $PG_STATUS — пробую пересоздать..."
        $DC stop postgres >/dev/null 2>&1
        $DC up -d postgres >/dev/null 2>&1
        sleep 5
        PG_STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$($DC ps -q postgres)" 2>/dev/null || echo "unknown")
        if [ "$PG_STATUS" = "healthy" ]; then
            ok "PostgreSQL healthy (после пересоздания)"
        else
            fail "PostgreSQL не стал healthy ($PG_STATUS) — проверьте логи: $DC logs postgres"
        fi
    fi
else
    fail "Контейнер PostgreSQL не найден"
fi

# Ждём healthy для Qdrant
info "Жду Qdrant healthy..."
QD_CONTAINER=$($DC ps -q qdrant 2>/dev/null || echo "")
if [ -n "$QD_CONTAINER" ]; then
    # Qdrant стартует быстро, ждём до 20 сек
    QD_HEALTHY=false
    for i in $(seq 1 20); do
        QD_STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$QD_CONTAINER" 2>/dev/null || echo "unknown")
        if [ "$QD_STATUS" = "healthy" ]; then
            QD_HEALTHY=true
            break
        fi
        sleep 1
    done
    if $QD_HEALTHY; then
        ok "Qdrant healthy"
    else
        warn "Qdrant статус: $QD_STATUS — пробую пересоздать..."
        $DC stop qdrant >/dev/null 2>&1
        $DC up -d qdrant >/dev/null 2>&1
        sleep 5
        QD_STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$($DC ps -q qdrant)" 2>/dev/null || echo "unknown")
        if [ "$QD_STATUS" = "healthy" ]; then
            ok "Qdrant healthy (после пересоздания)"
        else
            fail "Qdrant не стал healthy ($QD_STATUS) — проверьте логи: $DC logs qdrant"
        fi
    fi
else
    fail "Контейнер Qdrant не найден"
fi

# ══════════════════════════════════════════════════════════════════════════
# Шаг 4: Claude proxy (порт 8200)
# ══════════════════════════════════════════════════════════════════════════
step "Claude proxy (:8200)"

PROXY_DIR="$PROJECT_DIR/proxy"
PROXY_LOG="$PROXY_DIR/proxy.log"

if curl -sf http://localhost:8200/health >/dev/null 2>&1; then
    ok "Proxy уже запущен и отвечает"
else
    # Проверяем, не занят ли порт чем-то другим
    PORT_PID=$(lsof -ti :8200 2>/dev/null || true)
    if [ -n "$PORT_PID" ]; then
        PORT_CMD=$(ps -p "$PORT_PID" -o comm= 2>/dev/null || echo "unknown")
        warn "Порт 8200 занят процессом: $PORT_CMD (PID $PORT_PID)"
        warn "Убиваю процесс на порту 8200..."
        kill "$PORT_PID" 2>/dev/null || true
        sleep 1
    fi

    info "Запускаю Claude proxy..."

    # Проверяем зависимости proxy
    if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
        if [ -f "$PROXY_DIR/requirements.txt" ]; then
            info "Устанавливаю зависимости proxy..."
            pip install -q -r "$PROXY_DIR/requirements.txt" 2>/dev/null || \
                pip3 install -q -r "$PROXY_DIR/requirements.txt" 2>/dev/null || true
        fi
    fi

    # Запускаем proxy в фоне
    cd "$PROXY_DIR"
    nohup python3 -m uvicorn server:app --host 0.0.0.0 --port 8200 --log-level warning \
        > "$PROXY_LOG" 2>&1 &
    PROXY_PID=$!
    cd "$PROJECT_DIR"

    # Ждём ответа от /health
    if wait_for "Claude proxy" 10 curl -sf http://localhost:8200/health; then
        ok "Proxy запущен (PID $PROXY_PID), логи: proxy/proxy.log"
    else
        # Проверяем: жив ли процесс?
        if kill -0 "$PROXY_PID" 2>/dev/null; then
            warn "Proxy запущен (PID $PROXY_PID), но /health не отвечает"
            warn "Возможно, Claude CLI токен устарел. Проверьте: claude auth status"
            info "Логи: tail -f $PROXY_LOG"
        else
            fail "Proxy не удалось запустить"
            info "Логи:"
            tail -5 "$PROXY_LOG" 2>/dev/null | while read -r line; do
                info "  $line"
            done
            warn "Бот запустится, но LLM-запросы не будут работать!"
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# Шаг 5: Bot контейнер
# ══════════════════════════════════════════════════════════════════════════
step "Bot ($MODE)"

BUILD_FLAG=""
if $REBUILD; then
    BUILD_FLAG="--build"
    info "Полная пересборка (--build)..."
fi

$DC up -d $BUILD_FLAG bot 2>&1 | while read -r line; do
    info "$line"
done

# Даём боту время на старт (загрузка модели, подключение к БД)
info "Жду запуска бота (загрузка модели)..."
BOT_OK=false
for i in $(seq 1 30); do
    BOT_CONTAINER=$($DC ps -q bot 2>/dev/null || echo "")
    if [ -n "$BOT_CONTAINER" ]; then
        BOT_STATE=$(docker inspect --format='{{.State.Status}}' "$BOT_CONTAINER" 2>/dev/null || echo "unknown")
        if [ "$BOT_STATE" = "running" ]; then
            # Проверяем логи на наличие признаков старта
            if $DC logs --tail=20 bot 2>/dev/null | grep -qiE "(polling|started|running|bot started)"; then
                BOT_OK=true
                break
            fi
        elif [ "$BOT_STATE" = "exited" ] || [ "$BOT_STATE" = "dead" ]; then
            fail "Контейнер бота упал ($BOT_STATE)"
            info "Последние логи:"
            $DC logs --tail=15 bot 2>/dev/null | while read -r line; do
                info "  $line"
            done
            break
        fi
    fi
    sleep 2
done

if $BOT_OK; then
    ok "Бот запущен и работает"
else
    BOT_CONTAINER=$($DC ps -q bot 2>/dev/null || echo "")
    if [ -n "$BOT_CONTAINER" ]; then
        BOT_STATE=$(docker inspect --format='{{.State.Status}}' "$BOT_CONTAINER" 2>/dev/null || echo "unknown")
        if [ "$BOT_STATE" = "running" ]; then
            warn "Бот running, но не обнаружил сообщение о старте в логах"
            info "Возможно, загрузка модели ещё идёт. Проверьте:"
            info "  $DC logs -f bot"
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# Шаг 6: Итоговый статус
# ══════════════════════════════════════════════════════════════════════════
step "Итоговый статус"

echo ""

# PostgreSQL
PG_CONTAINER=$($DC ps -q postgres 2>/dev/null || echo "")
if [ -n "$PG_CONTAINER" ]; then
    PG_ST=$(docker inspect --format='{{.State.Health.Status}}' "$PG_CONTAINER" 2>/dev/null || echo "?")
    if [ "$PG_ST" = "healthy" ]; then ok "PostgreSQL: healthy"; else warn "PostgreSQL: $PG_ST"; fi
else
    fail "PostgreSQL: не найден"
fi

# Qdrant
QD_CONTAINER=$($DC ps -q qdrant 2>/dev/null || echo "")
if [ -n "$QD_CONTAINER" ]; then
    QD_ST=$(docker inspect --format='{{.State.Health.Status}}' "$QD_CONTAINER" 2>/dev/null || echo "?")
    if [ "$QD_ST" = "healthy" ]; then ok "Qdrant: healthy"; else warn "Qdrant: $QD_ST"; fi
else
    fail "Qdrant: не найден"
fi

# Claude proxy
if curl -sf http://localhost:8200/health >/dev/null 2>&1; then
    ok "Claude proxy: OK (:8200)"
else
    warn "Claude proxy: не отвечает"
fi

# Bot
BOT_CONTAINER=$($DC ps -q bot 2>/dev/null || echo "")
if [ -n "$BOT_CONTAINER" ]; then
    BOT_ST=$(docker inspect --format='{{.State.Status}}' "$BOT_CONTAINER" 2>/dev/null || echo "?")
    if [ "$BOT_ST" = "running" ]; then ok "Bot: running ($MODE)"; else fail "Bot: $BOT_ST"; fi
else
    fail "Bot: не найден"
fi

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

if $BOT_OK; then
    echo -e "${GREEN}${BOLD}  Бот запущен! Отправьте /start в @el_RAGozinBot${RESET}"
else
    echo -e "${YELLOW}${BOLD}  Бот в процессе запуска. Проверьте логи:${RESET}"
    echo -e "  ${DIM}$DC logs -f bot${RESET}"
fi

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"

# Полезные команды
echo ""
echo -e "${DIM}Полезные команды:${RESET}"
echo -e "  ${DIM}Логи бота:    $DC logs -f bot${RESET}"
echo -e "  ${DIM}Логи proxy:   tail -f proxy/proxy.log${RESET}"
echo -e "  ${DIM}Рестарт бота: $DC restart bot${RESET}"
echo -e "  ${DIM}Остановить:   ./start.sh --stop${RESET}"
echo -e "  ${DIM}Статус:       ./start.sh --status${RESET}"
echo ""

# ══════════════════════════════════════════════════════════════════════════
# --logs: показать логи бота в реальном времени
# ══════════════════════════════════════════════════════════════════════════
if $FOLLOW_LOGS; then
    echo -e "${DIM}(Ctrl+C для выхода из логов)${RESET}"
    $DC logs -f bot
fi
