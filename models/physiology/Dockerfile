# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install .

FROM base AS development

RUN python -m pip install -e ".[dev,train]"
COPY tests ./tests
COPY tools ./tools
COPY configs ./configs
COPY models ./models
COPY docs ./docs

CMD ["pytest"]

FROM base AS runtime

COPY configs ./configs
COPY models ./models
ENTRYPOINT ["dms-physiology-service"]
