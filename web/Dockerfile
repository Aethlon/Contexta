FROM oven/bun:1-alpine AS base
WORKDIR /app

COPY web/package.json web/bun.lock* web/package-lock.json* ./
RUN if [ -f bun.lock ]; then bun install --frozen-lockfile; else bun install; fi

FROM base AS dev
COPY web/ ./

FROM base AS builder
COPY web/ ./
RUN bun run build

FROM oven/bun:1-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["bun", "server.js"]
