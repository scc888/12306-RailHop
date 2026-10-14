# ==========================================
# Stage 1: Build Vue 3 Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Runtime Image (FastAPI + Nginx)
# ==========================================
FROM python:3.11-slim

# Switch Debian mirrors to Aliyun for fast apt downloads
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true && \
    apt-get update && \
    apt-get install -y --no-install-recommends nginx curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Install Python dependencies using Aliyun mirror
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# Copy backend application code and stations data
COPY backend/app /app/backend/app
COPY backend/data /app/backend/data

# Copy built frontend assets from stage 1
COPY --from=frontend-builder /build/dist /var/www/html

# Configure Nginx and entrypoint
RUN rm -f /etc/nginx/sites-enabled/*
COPY deploy/docker-nginx.conf /etc/nginx/conf.d/railhop.conf
COPY deploy/docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["/entrypoint.sh"]
