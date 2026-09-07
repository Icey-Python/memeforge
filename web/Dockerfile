# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# memeforge web — Next.js studio (multi-stage: deps -> builder -> runner)
# The production `runner` stage is last, so it is the default build target;
# the `dev` stage (below) is selected explicitly by docker-compose.dev.yml.
#
#   production:  docker build -t memeforge-web ./web
#   dev target:  docker compose -f docker-compose.dev.yml up web
# ---------------------------------------------------------------------------

ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS base
ENV LEFTHOOK=0 \
    CI=1 \
    NEXT_TELEMETRY_DISABLED=1
RUN npm install -g pnpm@11.9.0
WORKDIR /app

# ---- deps: node_modules in /opt/node_modules -------------------------------
FROM base AS deps
WORKDIR /opt/app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN (printf 'nodeLinker: hoisted\n'; cat pnpm-workspace.yaml) > .tmp \
    && mv .tmp pnpm-workspace.yaml \
    && pnpm install --frozen-lockfile --ignore-scripts

# ---- builder: compile the production bundle --------------------------------
FROM base AS builder
WORKDIR /app
COPY --from=deps /opt/app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_SERVER_URL=http://localhost:8000
ENV NEXT_PUBLIC_SERVER_URL=${NEXT_PUBLIC_SERVER_URL}
RUN ./node_modules/.bin/next build && mkdir -p public

# ---- dev: hot-reloading studio (compose bind-mounts ./web over /app) -------
FROM base AS dev
WORKDIR /app
COPY --from=deps /opt/app/node_modules /opt/node_modules
ENV NODE_ENV=development \
    NODE_PATH=/opt/node_modules \
    PATH=/opt/node_modules/.bin:$PATH \
    NEXT_PUBLIC_SERVER_URL=http://localhost:8000
COPY . .
EXPOSE 3000
CMD ["next", "dev", "--turbopack"]

# ---- runner: minimal standalone image ---------------------------------------
FROM node:${NODE_VERSION}-alpine AS runner
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs
WORKDIR /app
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1
CMD ["node", "server.js"]
