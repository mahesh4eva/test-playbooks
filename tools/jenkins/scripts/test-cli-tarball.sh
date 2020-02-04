#!/usr/bin/env bash

set -euxo pipefail

INVENTORY=${INVENTORY:-''}
AW_REPO_URL=${AW_REPO_URL:-''}
VARS_FILE=${VARS_FILE:-playbooks/vars.yml}
PYTEST_NUMPROCESSES="8"

# -- Start
#
# shellcheck source=lib/common
source "$(dirname "${0}")"/lib/common
setup_python3_env 'cli_venv'

# Install the awx CLI pip tarball and run a quick test
if [[ -z "${AW_REPO_URL}" ]]; then
    AW_REPO_URL=$(retrieve_value_from_vars_file "${VARS_FILE}" aw_repo_url)
fi

pip install "${AW_REPO_URL}/cli/ansible-tower-cli-latest.tar.gz"
pip install -r scripts/requirements.install
pip install -r requirements.txt
AWXKIT_BRANCH=$(retrieve_version_branch "$(cat VERSION)")
pip install -qU "git+ssh://git@github.com/ansible/tower.git@${AWXKIT_BRANCH}#egg=awxkit[websockets]&subdirectory=awxkit"

if [[ -z "${INVENTORY}" ]]; then
    INVENTORY=$(retrieve_inventory_file)
fi
TOWER_HOST=$(retrieve_tower_server_from_inventory "${INVENTORY}")
CREDS=$(retrieve_credential_file "${INVENTORY}")

# Confirm what awx cli we are using
head -n1 "$(which awx)"

pytest -v -c config/api.cfg \
    --junit-xml=reports/junit/results-cli-tarball.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    tests/cli/test_help.py
