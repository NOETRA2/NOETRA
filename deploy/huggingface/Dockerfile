FROM node:26.3.0-bookworm-slim
WORKDIR /home/node/app
COPY --chown=node:node package.json package-lock.json ./
USER node
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY --chown=node:node dist ./dist
ENV HOST=0.0.0.0 PORT=7860 NODE_ENV=production
EXPOSE 7860
CMD ["node", "dist/apps/demo/src/server.js"]
