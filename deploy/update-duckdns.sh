#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${DOCMOLDER_DUCKDNS_ENV_FILE:-/etc/docmolder/duckdns.env}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing Duck DNS config: ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
. "${ENV_FILE}"
set +a

DUCKDNS_DOMAIN="${DUCKDNS_DOMAIN:-docmolder}"
DUCKDNS_TOKEN="${DUCKDNS_TOKEN:-}"
DUCKDNS_IP="${DUCKDNS_IP:-}"

if [ -z "${DUCKDNS_DOMAIN}" ]; then
  echo "DUCKDNS_DOMAIN is required in ${ENV_FILE}" >&2
  exit 1
fi

if [ -z "${DUCKDNS_TOKEN}" ] || [ "${DUCKDNS_TOKEN}" = "changeme" ]; then
  echo "DUCKDNS_TOKEN is missing in ${ENV_FILE}" >&2
  exit 1
fi

if [[ "${DUCKDNS_DOMAIN}${DUCKDNS_TOKEN}${DUCKDNS_IP}" == *$'\n'* ]] \
  || [[ "${DUCKDNS_DOMAIN}${DUCKDNS_TOKEN}${DUCKDNS_IP}" == *$'\r'* ]]; then
  echo "Duck DNS config values cannot contain newlines." >&2
  exit 1
fi

curl_config_quote() {
  printf '%s' "$1" | sed 's/[\\"]/\\&/g'
}

response="$({
  echo "fail"
  echo "silent"
  echo "show-error"
  echo "max-time = 20"
  echo 'url = "https://www.duckdns.org/update"'
  echo "get"
  printf 'data-urlencode = "domains=%s"\n' "$(curl_config_quote "${DUCKDNS_DOMAIN}")"
  printf 'data-urlencode = "token=%s"\n' "$(curl_config_quote "${DUCKDNS_TOKEN}")"
  if [ -n "${DUCKDNS_IP}" ]; then
    printf 'data-urlencode = "ip=%s"\n' "$(curl_config_quote "${DUCKDNS_IP}")"
  fi
} | curl --config -)"
if [ "${response}" != "OK" ]; then
  echo "Duck DNS update failed for ${DUCKDNS_DOMAIN}: ${response}" >&2
  exit 1
fi

echo "Duck DNS update OK for ${DUCKDNS_DOMAIN}.duckdns.org"
