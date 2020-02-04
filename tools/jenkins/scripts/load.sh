#!/usr/bin/env bash

set -euxo pipefail

# -- Start
#
# shellcheck source=lib/common
source "$(dirname "${0}")"/lib/common

setup_python3_env

pip install -Ur scripts/requirements.install
pip install -Ur requirements.txt
AWXKIT_BRANCH=$(retrieve_version_branch "$(cat VERSION)")
pip install -qU "git+ssh://git@github.com/ansible/tower.git@${AWXKIT_BRANCH}#egg=awxkit[websockets]&subdirectory=awxkit"

INVENTORY=$(retrieve_inventory_file)
TOWER_HOST="$(retrieve_tower_server_from_inventory "${INVENTORY}")"
CREDS=$(retrieve_credential_file "${INVENTORY}")
until is_tower_ready "https://${TOWER_HOST}"; do :; done

pytest -c config/load.cfg \
    --api-credentials="${CREDS}" \
    --base-url="https://${TOWER_HOST}"
