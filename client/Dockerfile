# Imagen del client: compila la SPA y la sirve con Caddy, que además reenvía /api (REST y
# WebSocket) al server por la red privada. Se construye desde la raíz del repositorio, porque el
# lockfile y el workspace de pnpm están ahí: docker build -f client/Dockerfile .

FROM node:22.23.3-alpine AS construccion
# Sin hooks de Git: la imagen no tiene .git y el prepare de la raíz instalaría husky.
ENV HUSKY=0
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY client/package.json client/
RUN pnpm install --frozen-lockfile --filter client
COPY client client
# URL pública para canonical y og:url (client/README.md). Opcional.
ARG VITE_SITE_URL
RUN pnpm --filter client build-only

FROM caddy:2.11.7-alpine
COPY client/Caddyfile /etc/caddy/Caddyfile
COPY --from=construccion /repo/client/dist /srv
