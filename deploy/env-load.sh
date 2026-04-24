#!/usr/bin/env bash

_docmolder_trim_env_value() {
  local value="$1"
  value="$(printf '%s' "${value}" | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')"
  printf '%s' "${value}"
}

_docmolder_expand_safe_env_value() {
  local value="$1"
  if [ -n "${VENV_DIR:-}" ]; then
    value="${value//\$\{VENV_DIR\}/${VENV_DIR}}"
    value="${value//\$VENV_DIR/${VENV_DIR}}"
  fi
  printf '%s' "${value}"
}

load_docmolder_env_file() {
  local env_file="$1"
  local line key value
  local quoted

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
    quoted=""
    case "${value}" in
      \"*\")
        value="${value#\"}"
        value="${value%\"}"
        quoted="double"
        ;;
      \'*\')
        value="${value#\'}"
        value="${value%\'}"
        quoted="single"
        ;;
      *)
        value="$(_docmolder_trim_env_value "${value}")"
        ;;
    esac
    if [ "${quoted}" != "single" ]; then
      value="$(_docmolder_expand_safe_env_value "${value}")"
    fi
    export "${key}=${value}"
  done < "${env_file}"
}
