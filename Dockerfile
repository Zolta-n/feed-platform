FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir gunicorn==21.2.0 -r requirements.txt

COPY niche/ niche/
COPY cli.py wsgi.py ./

# feeds/ → mounted at runtime from repo checkout (/app/feeds)
# data/  → mounted at runtime for SQLite persistence (/app/data)

ENV PYTHONUNBUFFERED=1

EXPOSE 8001

# --workers=1 is required: APScheduler runs inside the WSGI process.
# Multiple workers would launch duplicate pipeline jobs.
CMD ["gunicorn", "--workers=1", "--bind=0.0.0.0:8001", "--timeout=120", "wsgi:application"]
