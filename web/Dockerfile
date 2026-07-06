FROM node:22-alpine AS base
WORKDIR /app

COPY web/package.json web/package-lock.json* ./
RUN npm ci

FROM base AS dev
COPY web/ ./

FROM base AS builder
COPY web/ ./
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
