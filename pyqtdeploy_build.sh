#!/usr/bin/env bash
set -euo pipefail

APP_PDY=${1:-app.pdy}
SYSROOT_JSON=${2:-sysroot.json}
PLATFORM=${3:-}

if [[ -z "${PLATFORM}" ]]; then
  case "$(uname -s)" in
    Linux) PLATFORM="linux-64" ;;
    Darwin) PLATFORM="macos-64" ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="win-64" ;;
    *)
      echo "Не удалось определить платформу. Укажите вручную: linux-64 | macos-64 | win-64" >&2
      exit 1
      ;;
  esac
fi

SYSROOT_DIR="sysroot-${PLATFORM}"
BUILD_DIR="build-${PLATFORM}"

if [[ ! -f "${APP_PDY}" ]]; then
  echo "Файл проекта ${APP_PDY} не найден." >&2
  exit 1
fi

if [[ ! -f "${SYSROOT_JSON}" ]]; then
  echo "Файл sysroot ${SYSROOT_JSON} не найден." >&2
  exit 1
fi

if [[ ! -d "${SYSROOT_DIR}" ]]; then
  echo "Собираю sysroot для ${PLATFORM}..."
  pyqtdeploy-sysroot "${SYSROOT_JSON}"
fi

pyqtdeploy-build "${APP_PDY}"

pushd "${BUILD_DIR}" >/dev/null
../${SYSROOT_DIR}/host/bin/qmake
if [[ "${PLATFORM}" == win-* ]]; then
  nmake
else
  make
fi
popd >/dev/null
