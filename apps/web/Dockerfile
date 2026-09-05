# syntax=docker/dockerfile:1

# Lexoria web — multi-stage build of the SPA from the pnpm monorepo.
# BUILD CONTEXT IS THE REPO ROOT (see docker-compose.yml) so workspace
# packages (packages/api-client) and pnpm-workspace.yaml resolve; the final
# stage keeps only the static bundle for nginx. Runtime nginx configuration is
# bind-mounted from infra/nginx, so this image carries no nginx config.
#
# Assumes (frontend conventions): apps/web/package.json exists (@lexoria/web),
# a pnpm-lock.yaml is committed at the repo root, and the build outputs to
# apps/web/dist. Adjust if the real output dir differs.

FROM node:22-bookworm-slim AS build

# pnpm pinned via the root package.json "packageManager" field
RUN corepack enable && corepack prepare pnpm@11.17.0 --activate
WORKDIR /repo

COPY . .

# Frozen install: requires pnpm-lock.yaml at the repo root (committed).
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# Build the web app and its workspace dependencies (@lexoria/api-client).
RUN pnpm --filter @lexoria/web... build

FROM nginx:1.27-alpine
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
EXPOSE 80
