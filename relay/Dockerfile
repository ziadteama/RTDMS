# Multi-stage build for sahi-sos-relay
FROM node:22-slim AS builder

# Install git required by Baileys dependency
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Runtime stage
FROM node:22-slim AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy production node_modules from builder
COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./
COPY src ./src

# Create auth and data directories and assign ownership to node user
RUN mkdir -p /app/auth /app/data && \
    chown -R node:node /app

USER node

VOLUME ["/app/auth", "/app/data"]

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:8787/v1/health').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))"

CMD ["node", "--experimental-transform-types", "src/main.ts"]
