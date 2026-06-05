FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# niche.db + WAL files live on a mounted volume so they survive container restarts.
RUN mkdir -p /app/data

EXPOSE 8000

# Flask app served via gunicorn. wsgi.py exposes `application`.
# Single-process scheduler is disabled in production (SCHEDULER_ENABLED=false);
# the daily pipeline is triggered by DSM Task Scheduler. See DEPLOY_SYNOLOGY.md.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "120", "wsgi:application"]
