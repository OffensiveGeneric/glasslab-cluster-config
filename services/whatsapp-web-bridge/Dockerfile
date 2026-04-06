FROM node:22-bookworm-slim

WORKDIR /app

ENV NODE_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY services/whatsapp-web-bridge/package.json /app/package.json
RUN npm install --omit=dev

COPY services/whatsapp-web-bridge/app /app/app

EXPOSE 8098

CMD ["node", "app/index.mjs"]
