FROM alpine:3.22

RUN apk add --no-cache rsync

COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN chmod +x /docker-entrypoint.sh

EXPOSE 873

ENTRYPOINT ["/docker-entrypoint.sh"]