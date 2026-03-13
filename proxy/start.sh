#!/bin/bash
# Запуск Claude-прокси на порту 8200.
# Использует OAuth-токен из ~/.claude/.credentials.json
cd "$(dirname "$0")"
exec uvicorn server:app --host 0.0.0.0 --port 8200 --log-level info
