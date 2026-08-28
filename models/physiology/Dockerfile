# syntax=docker/dockerfile:1
# 3.11 is the reference environment and the floor the linters target. The Pi runs
# 3.13, so `verify-py313` builds this same tree against it to catch drift.
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS base

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
