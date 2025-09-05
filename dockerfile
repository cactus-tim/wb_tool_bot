FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates gcc libpq-dev netcat-openbsd postgresql-client tzdata \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV TZ=UTC \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD pgrep -f "python.*main.py" >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]