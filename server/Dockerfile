FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIONY_DB_PATH=/data/biony.sqlite3

# Roda como usuário comum; /data já nasce dele para o volume herdar o dono.
RUN useradd --create-home --uid 1000 biony && mkdir /data && chown biony:biony /data

WORKDIR /app
COPY pyproject.toml ./
COPY biony ./biony
RUN pip install --no-cache-dir .

USER biony
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "biony.main:app", "--host", "0.0.0.0", "--port", "8000"]
