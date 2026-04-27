#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${DOCMOLDER_VPS_APP_DIR:-/opt/docmolder/app}"
SITE_SOURCE="${APP_DIR}/deploy/static/docmolder-site"
SITE_ROOT="${DOCMOLDER_STATIC_SITE_ROOT:-/usr/share/nginx/docmolder}"
NGINX_CONF="${DOCMOLDER_STATIC_NGINX_CONF:-/etc/nginx/conf.d/docmolder.conf}"

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

sudo install -d -m 755 "${SITE_ROOT}"
sudo rm -rf "${SITE_ROOT:?}/"*
sudo cp -R "${SITE_SOURCE}/." "${SITE_ROOT}/"
sudo install -d -m 755 "${SITE_ROOT}/assets"
sudo cp -R "${APP_DIR}/assets/brand" "${SITE_ROOT}/assets/"
sudo find "${SITE_ROOT}" -type d -exec chmod 755 {} +
sudo find "${SITE_ROOT}" -type f -exec chmod 644 {} +

if [ ! -f "${NGINX_CONF}" ]; then
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
