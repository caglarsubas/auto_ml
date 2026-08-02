# Backend (Django)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies for python-magic
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 file build-essential gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy project
COPY . .

RUN chmod +x docker/backend-entrypoint.sh

EXPOSE 8001

CMD ["sh", "docker/backend-entrypoint.sh"]
