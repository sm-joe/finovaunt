# Read-only dashboard API image. The dashboard projection API uses Python's standard library.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FINOVAUNT_API_HOST=0.0.0.0 \
    FINOVAUNT_API_PORT=8787 \
    FINOPS_OUTPUT_DIR=artifacts-live

WORKDIR /app

# Copy application source, but never bake live scan artifacts or credentials into the image.
COPY src/ ./src/
COPY scripts/dashboard_api.py ./scripts/dashboard_api.py

RUN mkdir -p /app/artifacts-live \
    && groupadd --system --gid 10001 finovaunt \
    && useradd --system --uid 10001 --gid finovaunt --home-dir /nonexistent finovaunt \
    && chown -R finovaunt:finovaunt /app

USER 10001:10001
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=2)" || exit 1

CMD ["python", "scripts/dashboard_api.py"]
