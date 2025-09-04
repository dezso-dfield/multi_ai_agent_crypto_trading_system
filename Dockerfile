# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /macats

# deps first (better cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code
COPY . .

CMD ["python3", "main.py"]