# syntax=docker/dockerfile:1.7
# ── SANKET Frontend (Vite + React) ──────────────────────────────────────────
# Build with Node, serve with nginx alpine.

FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS builder
WORKDIR /app
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_ML_API_BASE_URL=/ml
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_ML_API_BASE_URL=${VITE_ML_API_BASE_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ── runtime ─────────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS runtime
RUN apk update && apk upgrade --no-cache && \
    apk add --no-cache curl tini && \
    addgroup -S sanket && adduser -S -G sanket sanket

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Drop nginx PID dir permissions for non-root operation
RUN chown -R sanket:sanket /var/cache/nginx /var/log/nginx /etc/nginx/conf.d && \
    touch /var/run/nginx.pid && chown sanket:sanket /var/run/nginx.pid && \
    sed -i 's/user  nginx;/user  sanket;/' /etc/nginx/nginx.conf

USER sanket
EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=4s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8080/healthz || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["nginx", "-g", "daemon off;"]
