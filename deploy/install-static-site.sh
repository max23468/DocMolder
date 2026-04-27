#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
SITE_SOURCE="${APP_DIR}/deploy/static/docmolder-site"
SITE_ROOT="${DOCMOLDER_STATIC_SITE_ROOT:-/usr/share/nginx/docmolder}"
NGINX_CONF="${DOCMOLDER_STATIC_NGINX_CONF:-/etc/nginx/conf.d/docmolder.conf}"
WEBHOOK_HOST="${DOCMOLDER_GITHUB_WEBHOOK_HOST:-127.0.0.1}"
WEBHOOK_PORT="${DOCMOLDER_GITHUB_WEBHOOK_PORT:-8123}"
WEBHOOK_PATH="${DOCMOLDER_GITHUB_WEBHOOK_PATH:-/webhooks/github/deploy}"
WEBHOOK_HEALTH_PATH="${DOCMOLDER_GITHUB_WEBHOOK_HEALTH_PATH:-/webhooks/github/healthz}"
CERT_DIR="${DOCMOLDER_LETSENCRYPT_CERT_DIR:-/etc/letsencrypt/live/docmolder.duckdns.org}"

while [ "${SITE_ROOT}" != "/" ] && [ "${SITE_ROOT%/}" != "${SITE_ROOT}" ]; do
  SITE_ROOT="${SITE_ROOT%/}"
done

if [ ! -d "${SITE_SOURCE}" ]; then
  echo "Missing static site source: ${SITE_SOURCE}" >&2
  exit 1
fi

case "${SITE_ROOT}" in
  /usr/share/nginx/*|/var/www/*) ;;
  *)
    echo "Unsafe DOCMOLDER_STATIC_SITE_ROOT: ${SITE_ROOT}" >&2
    echo "Use a dedicated subdirectory under /usr/share/nginx or /var/www." >&2
    exit 1
    ;;
esac

case "${SITE_ROOT}" in
  /usr/share/nginx|/var/www|*"/.."*|*"../"*|*" "*)
    echo "Unsafe DOCMOLDER_STATIC_SITE_ROOT: ${SITE_ROOT}" >&2
    exit 1
    ;;
esac

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx non disponibile: salto installazione sito statico DocMolder."
  exit 0
fi

HTTPS_READY=0
if [ -f "${CERT_DIR}/fullchain.pem" ] && [ -f "${CERT_DIR}/privkey.pem" ]; then
  HTTPS_READY=1
fi

sudo install -d -m 755 "${SITE_ROOT}"
sudo rm -rf "${SITE_ROOT:?}/"*
sudo cp -R "${SITE_SOURCE}/." "${SITE_ROOT}/"
sudo install -d -m 755 "${SITE_ROOT}/assets"
sudo cp -R "${APP_DIR}/assets/brand" "${SITE_ROOT}/assets/"
sudo find "${SITE_ROOT}" -type d -exec chmod 755 {} +
sudo find "${SITE_ROOT}" -type f -exec chmod 644 {} +

if [ "${HTTPS_READY}" -eq 1 ]; then
  sudo tee "${NGINX_CONF}" >/dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name docmolder.duckdns.org;

    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name docmolder.duckdns.org;
    client_max_body_size 1m;

    ssl_certificate ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key ${CERT_DIR}/privkey.pem;

    root ${SITE_ROOT};
    index index.html;

    location = /healthz {
        default_type text/plain;
        return 200 "ok\n";
    }

    location = ${WEBHOOK_HEALTH_PATH} {
        proxy_pass http://${WEBHOOK_HOST}:${WEBHOOK_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location = ${WEBHOOK_PATH} {
        limit_except POST { deny all; }

        proxy_pass http://${WEBHOOK_HOST}:${WEBHOOK_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-GitHub-Event \$http_x_github_event;
        proxy_set_header X-GitHub-Delivery \$http_x_github_delivery;
        proxy_set_header X-Hub-Signature-256 \$http_x_hub_signature_256;
    }

    location / {
        try_files \$uri /index.html;
    }
}
EOF
else
  sudo tee "${NGINX_CONF}" >/dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name docmolder.duckdns.org;

    root ${SITE_ROOT};
    index index.html;

    location = /healthz {
        default_type text/plain;
        return 200 "ok\n";
    }

    location / {
        try_files \$uri /index.html;
    }
}
EOF
fi

sudo nginx -t
sudo systemctl reload nginx
