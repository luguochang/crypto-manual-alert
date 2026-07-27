FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

ARG UV_VERSION=0.11.28
ARG PIP_VERSION=26.1.2
ARG LIBLZMA_VERSION=5.8.1-1+deb13u1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_RETRIES=10 \
    UV_HTTP_TIMEOUT=120 \
    PATH=/app/backend/.venv/bin:$PATH

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install --no-install-recommends --yes "liblzma5=${LIBLZMA_VERSION}" \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade \
      "pip==${PIP_VERSION}" \
      "uv==${UV_VERSION}" \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin app

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra aegra --no-install-project

COPY backend ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra aegra \
    && chown -R 10001:10001 /app/backend

USER 10001:10001

CMD ["python", "-m", "crypto_alert_v2.workers", "--worker-id", "production-worker"]
