FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    gnupg \
    lsb-release \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-spa \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg \
    && echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
       > /etc/apt/sources.list.d/postgresql.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16 \
    && rm -rf /var/lib/apt/lists/*

# Python deps (тяжёлые, кешируются пока requirements.txt не меняется)
COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.5.1+cpu \
      --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Предзагрузка модели во время сборки (запечь в образ, не скачивать при старте)
# HF_HOME=/app/models — вне volume-маунтов, не будет перекрыт при старте контейнера
# hf_transfer включён для максимальной скорости скачивания
ENV HF_HUB_ENABLE_HF_TRANSFER=1 \
    HF_HOME=/app/models
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-large'); \
print('Model cached successfully')"

# App code
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY app/ ./app/

# Qdrant static binary (musl, no shared-library deps)
# Скачан заранее на хосте: curl -L <github release>/qdrant-x86_64-unknown-linux-musl.tar.gz
# Ставится после pip install чтобы не сбивать кеш тяжёлых слоёв
COPY qdrant-bin /usr/local/bin/qdrant

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
