# Online public-core dependency builder. No application, datasets or secrets.
# The installation handoff pins the resulting private image, not this rebuild.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 file libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && pip check \
    && rm /tmp/requirements.lock
