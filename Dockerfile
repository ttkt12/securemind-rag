FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    TEAMS_BOT_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.12.0+cpu" \
    && python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -c constraints.txt -r requirements.txt

# Bundles the locally-built knowledge base (vector_db/ and document_catalog.json),
# which are intentionally untracked in Git. Run `python predeploy_check.py` before
# building so an empty/missing index is caught before the image ships.
# sharepoint_downloads/, token_cache.bin and .env are excluded via .dockerignore.
COPY . .

EXPOSE 8080

CMD ["python", "teams_bot.py"]
