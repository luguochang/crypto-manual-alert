FROM python:3.12-slim

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

CMD ["jiami-alert", "--config", "config/default.yaml", "--config", "config/prod.yaml", "scheduler"]

