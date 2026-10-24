# Web V2 (Next.js) image — separate service on purpose.
#
# The Python image must not gain Node (supply-chain decision in ADR-001 and
# .dockerignore). This image only serves the UI shell: it holds no scan
# secrets, no LLM key and no database. The API authority stays in FastAPI.
#
# Build from the web/ directory:
#   docker build -t metatracer-web-v2 ./web

########## deps: install once, full toolchain (build needs it) ##########
FROM node:24-alpine AS deps

WORKDIR /app
# `npm ci` fails on a drifted lockfile: reproducible by construction.
COPY package.json package-lock.json ./
RUN npm ci


########## builder: compile the standalone server ##########
FROM node:24-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `output: 'standalone'` (next.config.ts) emits a self-contained server under
# .next/standalone so the runtime image needs no node_modules tree.
RUN npm run build


########## runtime: minimal, non-root ##########
FROM node:24-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# Standalone output: server.js + the minimal node_modules it needs + static.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# Public assets (theme-init.js, favicon) are served by Next itself.
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

# The API origin is injected at runtime; nothing is baked into the bundle.
ENV METATRACER_API_ORIGIN=http://127.0.0.1:8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/v2').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["node", "server.js"]