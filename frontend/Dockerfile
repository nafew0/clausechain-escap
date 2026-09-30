# ClauseChain frontend image (Next.js 16 / Node 24, per package.json "engines").
# BACKEND_URL and NEXT_PUBLIC_API_URL are read by next.config.ts at build
# time (rewrites() + inlined NEXT_PUBLIC_* vars) — both must be supplied as
# build args, not just runtime env, or `next build` fails/embeds the wrong
# values. Build context is this frontend/ directory.
FROM node:24-slim AS deps
WORKDIR /srv/clausechain/frontend
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /srv/clausechain/frontend
COPY --from=deps /srv/clausechain/frontend/node_modules ./node_modules
COPY . .

ARG BACKEND_URL=http://backend:8001
ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_DJANGO_ADMIN_URL=
ENV NODE_ENV=production \
    BACKEND_URL=${BACKEND_URL} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_DJANGO_ADMIN_URL=${NEXT_PUBLIC_DJANGO_ADMIN_URL}
RUN npm run build

FROM node:24-slim AS runtime
WORKDIR /srv/clausechain/frontend
ENV NODE_ENV=production
COPY --from=builder /srv/clausechain/frontend/public ./public
COPY --from=builder /srv/clausechain/frontend/.next ./.next
COPY --from=builder /srv/clausechain/frontend/node_modules ./node_modules
COPY --from=builder /srv/clausechain/frontend/package.json ./package.json
COPY --from=builder /srv/clausechain/frontend/next.config.ts ./next.config.ts

EXPOSE 3000
CMD ["npm", "start"]
