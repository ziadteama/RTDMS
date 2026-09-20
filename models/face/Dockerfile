# syntax=docker/dockerfile:1
# 3.11 is the reference environment. The Pi runs 3.13 — verify-py313 catches drift.
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

# System libs MediaPipe / OpenCV expect on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install .

FROM base AS development

RUN python -m pip install -e ".[dev,bench]"
COPY tests ./tests
COPY tools ./tools
COPY configs ./configs
COPY models ./models
COPY docs ./docs
COPY run.py bench.py calibrate_camera.py ./

CMD ["pytest"]

FROM base AS runtime

COPY models ./models
COPY configs ./configs
COPY run.py ./
CMD ["python", "run.py", "--no-display", "--no-alerts"]
