# Frontend (Angular)
# Use Debian-based image to avoid occasional esbuild deadlocks on Alpine
FROM node:24-bookworm

WORKDIR /app

# Install dependencies first (better layer caching)
COPY frontend/package*.json ./
COPY frontend/vendor/ ./vendor/
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund --maxsockets=5

# Copy the rest of the app
COPY frontend/ .

EXPOSE 4300

# Improve file watching stability inside Docker
ENV CHOKIDAR_USEPOLLING=true

CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4300", "--poll", "2000"]
