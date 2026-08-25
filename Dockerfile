FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# Shell form so $PORT is expanded by the shell at container start (Render
# injects PORT at runtime, not build time). Falls back to 8000 if unset,
# e.g. for local `docker run` without -e PORT.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
