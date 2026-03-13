#!/bin/bash
set -e

PGDATA=/var/lib/postgresql/data
PGLOG=/tmp/postgresql.log
PGBIN=/usr/lib/postgresql/16/bin
PG_USER="${POSTGRES_USER:-ragbot}"
PG_PASS="${POSTGRES_PASSWORD:-ragbot_secret}"
PG_DB="${POSTGRES_DB:-ragbot}"

# ── PostgreSQL ──────────────────────────────────────────────────────────────
FRESH_INIT=0
if [ ! -f "$PGDATA/PG_VERSION" ]; then
    echo "==> Initializing PostgreSQL (first start)..."
    install -d -o postgres -m 0700 "$PGDATA"
    # initdb выполняется от postgres OS-юзера → суперюзер в кластере = postgres
    su -s /bin/sh postgres -c \
        "$PGBIN/initdb -D $PGDATA --auth=trust --no-locale --encoding=UTF8"
    FRESH_INIT=1
fi

echo "==> Starting PostgreSQL..."
chown -R postgres:postgres "$PGDATA"

# Совместимость с кластерами, созданными на alpine (locale en_US.utf8 не доступна в Debian slim)
if [ -f "$PGDATA/postgresql.conf" ]; then
    sed -i \
        -e "s/lc_messages = 'en_US.utf8'/lc_messages = 'C'/g" \
        -e "s/lc_monetary = 'en_US.utf8'/lc_monetary = 'C'/g" \
        -e "s/lc_numeric = 'en_US.utf8'/lc_numeric = 'C'/g" \
        -e "s/lc_time = 'en_US.utf8'/lc_time = 'C'/g" \
        "$PGDATA/postgresql.conf"
fi

# Останавливаем уже запущенный экземпляр (на случай рестарта контейнера)
su -s /bin/sh postgres -c "$PGBIN/pg_ctl -D $PGDATA stop -m fast" 2>/dev/null || true

su -s /bin/sh postgres -c "$PGBIN/pg_ctl -D $PGDATA -l $PGLOG start -w"

# При свежей инициализации создаём пользователя и БД
# (при миграции со старого контейнера они уже существуют — пропускаем)
if [ "$FRESH_INIT" = "1" ]; then
    echo "==> Creating database user and database..."
    su -s /bin/sh postgres -c \
        "$PGBIN/psql postgres -c \"CREATE USER $PG_USER WITH PASSWORD '$PG_PASS';\""
    su -s /bin/sh postgres -c \
        "$PGBIN/createdb -O $PG_USER $PG_DB"
fi

# ── Qdrant ──────────────────────────────────────────────────────────────────
echo "==> Starting Qdrant..."
mkdir -p /var/lib/qdrant/storage
QDRANT__SERVICE__HOST=127.0.0.1 \
QDRANT__SERVICE__HTTP_PORT=6333 \
QDRANT__STORAGE__STORAGE_PATH=/var/lib/qdrant/storage \
/usr/local/bin/qdrant &>/tmp/qdrant.log &

echo "==> Waiting for Qdrant..."
until bash -c 'echo > /dev/tcp/localhost/6333' 2>/dev/null; do sleep 1; done
echo "==> Qdrant ready"

# ── Migrations ──────────────────────────────────────────────────────────────
echo "==> Running Alembic migrations..."
alembic upgrade head

# ── Dependencies check ──────────────────────────────────────────────────────
if ! python -c "import pymorphy3" 2>/dev/null; then
    echo "==> Installing pymorphy3 (not in image)..."
    pip install -q pymorphy3 pymorphy3-dicts-ru
fi

# ── Bot ─────────────────────────────────────────────────────────────────────
echo "==> Starting bot..."
exec python -m app.main
