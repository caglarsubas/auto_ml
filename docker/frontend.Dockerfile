# Frontend (Angular)
# Use Debian-based image to avoid occasional esbuild deadlocks on Alpine
FROM node:20-bullseye

WORKDIR /app

# Install dependencies first (better layer caching)
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the app
COPY frontend/ .

EXPOSE 4300

# Improve file watching stability inside Docker
ENV CHOKIDAR_USEPOLLING=true

CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4300", "--poll", "2000"]
