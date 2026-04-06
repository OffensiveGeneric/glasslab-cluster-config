FROM node:22

WORKDIR /app

ENV NODE_ENV=production

COPY services/whatsapp-web-bridge/package.json /app/package.json
COPY services/whatsapp-web-bridge/package-lock.json /app/package-lock.json
RUN npm ci --omit=dev

COPY services/whatsapp-web-bridge/app /app/app

EXPOSE 8098

CMD ["node", "app/index.mjs"]
