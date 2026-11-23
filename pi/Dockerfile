ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY fusion /app/fusion
COPY models/physiology/pyproject.toml models/physiology/README.md /app/models/physiology/
COPY models/physiology/src /app/models/physiology/src
COPY models/physiology/models/hr_shadow_mpddf_v1.json /app/models/physiology/models/
COPY contracts /app/contracts
COPY pi /app/pi
RUN pip install -e /app/fusion -e /app/models/physiology -e '/app/pi[dev]'
WORKDIR /app/pi
CMD ["sh", "-c", "pytest && ruff check . && mypy src"]
