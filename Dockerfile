# ── Stage 1 : builder ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN pip install uv

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# Installe les dépendances dans un venv isolé
RUN uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python \
    fastapi uvicorn[standard] httpx pydantic pydantic-settings anthropic structlog slowapi aiosqlite hatchling

# ── Stage 2 : image finale ─────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src/ src/

# Volume pour SQLite city_cache
VOLUME ["/storage"]

EXPOSE 80

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    STORAGE_DIR="/storage"

CMD ["uvicorn", "route_compare.main:app", "--host", "0.0.0.0", "--port", "80"]
