FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/azure/run-ingestion-worker.sh /app/azure/run-alert-worker.sh /app/azure/run-chile-region-backfill.sh /app/azure/run-chile-region-report.sh /app/azure/run-chile-region-manual-patch.sh /app/azure/run-tracking-alerts-worker.sh /app/azure/run-tracking-date-refresh-worker.sh

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
