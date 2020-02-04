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
pip install -Ur collection-test-requirements.txt
pip install -U "git+ssh://git@github.com/${AWXKIT_FORK}/${AWXKIT_REPO}.git@${AWXKIT_BRANCH}#egg=awxkit[formatting,websockets]&subdirectory=awxkit"

if [[ -z "${AW_REPO_URL}" ]]; then
    AW_REPO_URL=$(retrieve_value_from_vars_file "${VARS_FILE}" aw_repo_url)
fi

if [[ -z "${INVENTORY}" ]]; then
    INVENTORY=$(retrieve_inventory_file)
fi
TOWER_HOST=$(retrieve_tower_server_from_inventory "${INVENTORY}")
CREDS=$(retrieve_credential_file "${INVENTORY}")

# Setup the venvs and collection for the collection tests
ansible-playbook -v -i "$INVENTORY" -l 'local,tower' -e "venv_base=/var/lib/awx/venv venv_folder_name=python2_tower_modules remote_python=python2 venv_packages='ansible-tower-cli psutil git+https://github.com/ansible/ansible.git'" playbooks/create_custom_virtualenv.yml
ansible-playbook -v -i "$INVENTORY" -l 'local,tower' -e "venv_base=/var/lib/awx/venv venv_folder_name=python3_tower_modules remote_python=python36 venv_packages='ansible-tower-cli psutil git+https://github.com/ansible/ansible.git'" playbooks/create_custom_virtualenv.yml
ansible-playbook -v -i "$INVENTORY" -l 'local,tower' -e "product=$PRODUCT aw_repo_url=$AW_REPO_URL ansible_galaxy_bin='/var/lib/awx/venv/python3_tower_modules/bin/ansible-galaxy'" playbooks/setup-collection-tests.yml

set +e

# Run tests that need to run serially
pytest -v -c config/api.cfg \
    --junit-xml=reports/junit/results-collection-serial.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    -k "serial${TESTEXPR}" \
    tests/collection

# Run parallel tests
pytest -v -c config/api.cfg \
    --junit-xml=reports/junit/results-collection-parallel.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    -n "${PYTEST_NUMPROCESSES}" \
    --dist=loadfile \
    -k "not serial${TESTEXPR}" \
    tests/collection

# Workaround https://github.com/pytest-dev/pytest-xdist/issues/445
./scripts/prefix_lastfailed "$(find .pytest_cache -name lastfailed)"
pytest --cache-show "cache/lastfailed"

# Rerun any failures to check for flake
pytest -v -c config/api.cfg \
    --last-failed --last-failed-no-failures none \
    --junit-xml=reports/junit/results-collection-rerun.xml \
    --ansible-host-pattern="${TOWER_HOST}" \
    --ansible-inventory="${INVENTORY}" \
    --api-credentials="${CREDS}" \
    --github-cfg="${CREDS}" \
    --base-url="https://${TOWER_HOST}" \
    tests/collection

# Run the sanity tests
sudo mkdir -p /usr/share/ansible/collections/ansible_collections/awx/awx/tests/output
sudo chown ec2-user /usr/share/ansible/collections/ansible_collections/awx/awx/tests/output

pushd /usr/share/ansible/collections/ansible_collections/awx/awx
ansible-test sanity --junit
popd

./scripts/merge_junit \
    reports/junit/results{-collection-serial,-collection-parallel,-collection-rerun}.xml \
    /usr/share/ansible/collections/ansible_collections/awx/awx/tests/output/junit/*.xml \
    reports/junit/results-collection.xml

set -e
