# Imagen única del pipeline: ingest -> dbt build -> publish (python -m pipeline.run).
# Sin red en tiempo de ejecución: la extensión httpfs de DuckDB se instala aquí, al construir.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/home/pipeline \
    WORK_DIR=/work \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

RUN pip install --no-cache-dir uv==0.9.0 \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin pipeline \
    && mkdir -p /app /work \
    && chown -R pipeline:pipeline /app /work

WORKDIR /app
USER pipeline

# Dependencias primero (capa cacheable), luego el código.
COPY --chown=pipeline:pipeline pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=pipeline:pipeline src ./src
COPY --chown=pipeline:pipeline dbt ./dbt
COPY --chown=pipeline:pipeline scripts ./scripts
RUN uv sync --frozen --no-dev

# Extensión de DuckDB para leer/escribir S3, instalada una vez en la imagen.
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs')"

# Los secretos (PSEUDONYM_KEY, credenciales) llegan por entorno/Secrets Manager; nada se hornea en la imagen.
ENTRYPOINT ["python", "-m", "pipeline.run"]
