#!/bin/sh

apk add --no-cache openssl curl

SSL_DIR=/etc/nginx/ssl

mkdir -p $SSL_DIR

if [ ! -f $SSL_DIR/server.crt ] || [ ! -f $SSL_DIR/server.key ]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -nodes -days 365 \
        -subj "/CN=localhost" \
        -newkey rsa:2048 \
        -keyout $SSL_DIR/server.key \
        -out $SSL_DIR/server.crt
fi

echo "Waiting for app to be ready..."
while ! curl -f http://admin:8080/health > /dev/null 2>&1; do
    echo "App not ready yet, waiting..."
    sleep 5
done

echo "App is ready, starting nginx..."

nginx -g "daemon off;"