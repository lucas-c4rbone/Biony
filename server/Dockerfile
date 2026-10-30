FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BIONY_DB_PATH=/data/biony.sqlite3 \
    BIONY_HOME_CONFIG=/config/casa.toml \
    BIONY_MODELS_DIR=/data/models \
    HF_HUB_DISABLE_TELEMETRY=1

# libgomp: paralelismo (OpenMP) usado pelo Whisper e pelo Piper.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Roda como usuário comum; /data já nasce dele para o volume herdar o dono.
RUN useradd --create-home --uid 1000 biony && mkdir /data && chown biony:biony /data

WORKDIR /app
COPY pyproject.toml ./
COPY biony ./biony
# Os modelos de voz não entram na imagem: são baixados no 1º start para o volume /data.
RUN pip install --no-cache-dir ".[voz]"

USER biony
EXPOSE 8000
# start-period longo: no primeiro start o Whisper (~500 MB) é baixado.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10m \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "biony.main:app", "--host", "0.0.0.0", "--port", "8000"]
