ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml /app/
COPY src /app/src
COPY config /app/config
COPY third_party /app/third_party
COPY tests/fixtures /app/tests/fixtures

RUN pip install --upgrade pip && pip install .

RUN mkdir -p /app/data

CMD ["crypto-alert", "--config", "config/default.yaml", "--config", "config/prod.yaml", "--config", "config/staging.yaml", "scheduler"]
