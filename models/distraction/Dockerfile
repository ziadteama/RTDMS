# syntax=docker/dockerfile:1
# Verify image: unit tests + lint. The rule engine, smoothing, ROI maths and decode are pure
# numpy/OpenCV, so no MediaPipe / ncnn / Ultralytics is needed here.
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install .

FROM base AS development
RUN python -m pip install -e ".[dev]"
COPY configs ./configs
COPY scripts ./scripts
COPY tests ./tests
CMD ["pytest"]
