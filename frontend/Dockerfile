FROM docker.artifactory.ssn.juniper.net/node:20-alpine AS dev

WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM docker.artifactory.ssn.juniper.net/node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tsconfig.json vite.config.build.ts index.html ./
COPY src ./src
RUN npm run build

FROM docker.artifactory.ssn.juniper.net/caddy:alpine AS prod

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /usr/share/caddy

EXPOSE 80
