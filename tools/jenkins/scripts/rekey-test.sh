#!/usr/bin/env bash

set -euxo pipefail

# shellcheck source=lib/common
source "$(dirname "${0}")"/lib/common

AWXKIT_FORK=${AWXKIT_FORK:-ansible}
AWXKIT_BRANCH=${AWXKIT_BRANCH:-$(retrieve_version_branch "$(cat VERSION)")}
AWXKIT_REPO=${AWXKIT_REPO:-tower}
VARS_FILE=${VARS_FILE:-playbooks/vars.yml}

# -- Start
#
setup_python3_env

pip install -qUr scripts/requirements.install
pip install -qUr requirements.txt
pip install -qU "git+ssh://git@github.com/${AWXKIT_FORK}/${AWXKIT_REPO}.git@${AWXKIT_BRANCH}#egg=awxkit[websockets]&subdirectory=awxkit"

echo "y" | pip uninstall pytest-mp || true

INVENTORY=$(retrieve_inventory_file)
TOWER_HOST=$(retrieve_tower_server_from_inventory "${INVENTORY}")
CREDS=$(retrieve_credential_file "${INVENTORY}")
REKEY_CHECK="${REKEY_CHECK:-load}"

if [[ "${REKEY_CHECK}" = "load" ]]; then
    export AWXKIT_PREVENT_TEARDOWN=1
fi

set +e
pytest -vv -c config/api.cfg \
    --junit-xml="reports/junit/results-rekey-${REKEY_CHECK}.xml" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    "tests/rekey/test_${REKEY_CHECK}.py"
set -e
