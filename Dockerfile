FROM python:3.13-slim AS builder

ARG OBSURA_SPACY_MODELS="en_core_web_sm es_core_news_sm"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install .[presidio] \
    && if [ -n "$OBSURA_SPACY_MODELS" ]; then \
        for model in $OBSURA_SPACY_MODELS; do \
          python -m spacy download "$model"; \
        done; \
      fi


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    OBSURA_ENVIRONMENT=production

LABEL org.opencontainers.image.title="obsura-api" \
      org.opencontainers.image.description="Obsura API development image" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system obsura \
    && useradd --system --gid obsura --home-dir /app --create-home obsura \
    && mkdir -p /app/data /app/storage \
    && chown -R obsura:obsura /app

COPY --from=builder /opt/venv /opt/venv

USER obsura

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/ready', timeout=5)"

CMD ["uvicorn", "obsura_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
