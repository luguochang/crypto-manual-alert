FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ARG UV_VERSION=0.11.28

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_RETRIES=10 \
    UV_HTTP_TIMEOUT=120 \
    PATH=/app/backend/.venv/bin:$PATH

WORKDIR /app/backend

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

CMD ["python", "-m", "crypto_alert_v2.workers", "--worker-id", "container-worker"]
