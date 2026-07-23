#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="${DOCMOLDER_PYTHON_RUNTIME_VERSION:-3.13.14}"
PYTHON_SHA256="${DOCMOLDER_PYTHON_RUNTIME_SHA256:-639e43243c620a308f968213df9e00f2f8f62332f7adbaa7a7eeb9783057c690}"
PYTHON_PREFIX="${DOCMOLDER_PYTHON_RUNTIME_PREFIX:-/opt/python/${PYTHON_VERSION}}"
PYTHON_URL="https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz"
PYTHON_SYMLINK="${DOCMOLDER_PYTHON_RUNTIME_SYMLINK:-/usr/local/bin/python3.13}"

install_build_dependencies() {
  if ! command -v apt >/dev/null 2>&1; then
    echo "Unsupported package manager: expected apt for the Python 3.13 runtime installer." >&2
    exit 1
  fi

  sudo apt update
  sudo apt install -y \
    build-essential \
    curl \
    libbz2-dev \
    libdb-dev \
    libexpat1-dev \
    libffi-dev \
    libgdbm-dev \
    liblzma-dev \
    libncursesw5-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    tk-dev \
    uuid-dev \
    xz-utils \
    zlib1g-dev
}

if [ -x "${PYTHON_PREFIX}/bin/python3.13" ]; then
  sudo ln -sfn "${PYTHON_PREFIX}/bin/python3.13" "${PYTHON_SYMLINK}"
  "${PYTHON_SYMLINK}" --version
  exit 0
fi

install_build_dependencies

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

archive="${work_dir}/Python-${PYTHON_VERSION}.tar.xz"
curl -fsSL "${PYTHON_URL}" -o "${archive}"
printf '%s  %s\n' "${PYTHON_SHA256}" "${archive}" | sha256sum -c -

tar -C "${work_dir}" -xf "${archive}"
cd "${work_dir}/Python-${PYTHON_VERSION}"

./configure --prefix="${PYTHON_PREFIX}" --with-ensurepip=install
make -j"$(nproc)"
sudo make install
sudo ln -sfn "${PYTHON_PREFIX}/bin/python3.13" "${PYTHON_SYMLINK}"

"${PYTHON_SYMLINK}" --version
