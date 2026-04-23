#!/usr/bin/env bash

load_docmolder_env_file() {
  local env_file="$1"
  local line key value

  if [ ! -f "${env_file}" ]; then
    return 0
  fi

  while IFS= read -r line || [ -n "${line}" ]; do
    line="${line%$'\r'}"
    case "${line}" in
      ""|\#*)
        continue
        ;;
    esac

    key="${line%%=*}"
    if [ "${key}" = "${line}" ]; then
      continue
    fi

    case "${key}" in
      DOCMOLDER_*)
        ;;
      *)
        continue
        ;;
    esac

    if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi

    value="${line#*=}"
    case "${value}" in
      \"*\")
        value="${value#\"}"
        value="${value%\"}"
        ;;
      \'*\')
        value="${value#\'}"
        value="${value%\'}"
        ;;
    esac
    export "${key}=${value}"
  done < "${env_file}"
}
