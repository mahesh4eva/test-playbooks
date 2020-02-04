#!/usr/bin/env bash

set -euxo pipefail

# shellcheck source=lib/common
source "$(dirname "${0}")"/lib/common

TESTEXPR=${TESTEXPR:-''}
INVENTORY=${INVENTORY:-''}
AW_REPO_URL=${AW_REPO_URL:-''}
TOWER_FORK=${TOWER_FORK:-'ansible'}
TOWER_BRANCH=${TOWER_BRANCH:-$(retrieve_version_branch "$(cat VERSION)")}
PRODUCT=${PRODUCT:-'awx'}
AWXKIT_FORK=${TOWERKIT_FORK:-${TOWER_FORK}}
AWXKIT_BRANCH=${TOWERKIT_BRANCH:-${TOWER_BRANCH}}
AWXKIT_REPO=${AWXKIT_REPO:-${PRODUCT}}
VARS_FILE=${VARS_FILE:-playbooks/vars.yml}
PYTEST_NUMPROCESSES="8"

if [[ -n "${TESTEXPR}" ]]; then
    TESTEXPR=" and (${TESTEXPR})"
fi

# -- Start
#
setup_python3_env

pip install -Ur scripts/requirements.install
pip install -Ur requirements.txt
pip install -U "git+ssh://git@github.com/${AWXKIT_FORK}/${AWXKIT_REPO}.git@${AWXKIT_BRANCH}#egg=awxkit[formatting,websockets]&subdirectory=awxkit"

# We need to install the ansible-tower-cli package at this point as during
# test-runner setup it may not be ready
if [[ -z "${AW_REPO_URL}" ]]; then
    AW_REPO_URL=$(retrieve_value_from_vars_file "${VARS_FILE}" aw_repo_url)
fi
ansible-playbook --become -v -i playbooks/inventory.log -e "aw_repo_url=${AW_REPO_URL}" playbooks/test_runner/install_cli_repo.yml

sudo yum install --enablerepo='ansible-tower-cli' -y ansible-tower-cli

# Try remove the virtualenv awx binary to guarantee we use the one installed by
# the RPM
rm -f ${VIRTUAL_ENV}/bin/awx

# Confirm what awx cli we are using
head -n1 `which awx`

if [[ -z "${INVENTORY}" ]]; then
    INVENTORY=$(retrieve_inventory_file)
fi
TOWER_HOST=$(retrieve_tower_server_from_inventory "${INVENTORY}")
CREDS=$(retrieve_credential_file "${INVENTORY}")

set +e

# Run tests that need to run serially
pytest -v -c config/api.cfg \
    --junit-xml=reports/junit/results-cli-serial.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    -k "serial${TESTEXPR}" \
    tests/cli

# Run parallel tests
pytest -v -c config/api.cfg \
    --junit-xml=reports/junit/results-cli-parallel.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    -n "${PYTEST_NUMPROCESSES}" \
    --dist=loadfile \
    -k "not serial${TESTEXPR}" \
    tests/cli

# Workaround https://github.com/pytest-dev/pytest-xdist/issues/445
./scripts/prefix_lastfailed "$(find .pytest_cache -name lastfailed)"
pytest --cache-show "cache/lastfailed"

# Rerun any failures to check for flake
pytest -v -c config/api.cfg \
    --last-failed --last-failed-no-failures none \
    --junit-xml=reports/junit/results-cli-rerun.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    tests/cli

./scripts/merge_junit \
    reports/junit/results{-cli-serial,-cli-parallel,-cli-rerun,-cli}.xml

set -e
