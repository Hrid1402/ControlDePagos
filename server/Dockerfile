# Imagen del server: la usan la API, el worker y Beat, cada uno con su comando de arranque
# (server/railway*.json). Sin uv ni pnpm en la imagen final: el .venv va en el PATH.

FROM python:3.12.15-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS construccion
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
# Primero solo las dependencias, para que esta capa se reutilice mientras no cambie el lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
RUN uv sync --locked --no-dev

FROM base
RUN useradd --create-home --uid 10001 app
COPY --from=construccion --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER app
EXPOSE 8000
# Railway asigna PORT. El server solo recibe tráfico del client por la red privada, por eso
# confía en las cabeceras de proxy de cualquier origen.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips '*'"]
