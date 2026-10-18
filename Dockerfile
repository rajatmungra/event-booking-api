FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

# Keep the venv outside /app so the project folder mounted by compose can't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_DEV=1 \
    UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /app

# Install dependencies first so this layer is cached when only app code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-cache

COPY . .

EXPOSE 8000
# --no-access-log: our middleware already logs every request (as JSON, with its request id).
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
