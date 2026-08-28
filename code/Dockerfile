FROM nginx:1.27-alpine

RUN rm -rf /usr/share/nginx/html/*

COPY web_application/index.html web_application/styles.css web_application/app.js /usr/share/nginx/html/

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
