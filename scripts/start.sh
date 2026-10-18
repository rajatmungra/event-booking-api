#!/bin/sh
# Production start command (used by render.yaml). Local development uses the Dockerfile's CMD.
set -e

# Apply migrations before serving traffic, so the code never runs against an older schema.
uv run alembic upgrade head

# --proxy-headers: behind Render's proxy, take the client IP from X-Forwarded-For (the login rate
# limit is per client IP). "*" trusts any proxy, which is fine because only Render's proxy can
# reach the container. Render sets $PORT.
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --no-access-log --proxy-headers --forwarded-allow-ips="*"
