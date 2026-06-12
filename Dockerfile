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
    && python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.2.2+cpu" \
    && python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -c constraints.txt -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "teams_bot.py"]
