from awxkit.config import config

import pytest
import json
import os

from tests.api import APITest
from tests.collection import CUSTOM_VENVS, CUSTOM_VENVS_NAMES

TOWER_MODULES_PARAMS = [
    'credential',
    'credential_type',
    'group',
    'host',
    'inventory',
    'inventory_source',
    'job_cancel',
    'job_launch',
    'job_list',
    'job_template',
    'job_wait',
    'label',
    'notification',
    'project',
    'project_manual',
    pytest.param('receive', marks=pytest.mark.serial),
    'role',
    'send',
    'settings',
    'team',
    'user',
    'workflow_template',
]


@pytest.fixture
def tower_credential(factories):
    return factories.credential(kind='tower', username=config.credentials.default.username,
                                password=config.credentials.default.password, host=config.base_url)


# FIXME Remove "skip_if_cluster" fixture. We must skip if cluster right now
# because the node we're installing awx collection on doesn't have access to
# the tower repo in a cluster deployment.
@pytest.mark.fixture_args(venvs=CUSTOM_VENVS, cluster=True)
@pytest.mark.usefixtures('skip_if_pre_ansible29', 'skip_if_openshift', 'authtoken', 'skip_if_cluster', 'skip_if_wrong_python')
@pytest.mark.parametrize('python_venv', CUSTOM_VENVS, ids=CUSTOM_VENVS_NAMES)
class Test_Ansible_Tower_Modules_via_Playbooks(APITest):
    @pytest.mark.parametrize('tower_module', TOWER_MODULES_PARAMS)
    def test_ansible_tower_module(self, factories, tower_module, project, tower_credential, venv_path, python_venv, is_cluster, collection_fqcn):
        """
        Ansible modules that interact with Tower live in an Ansible Collection.
        This test invokes the integration tests that ran in Ansible core CI
        before it was split out into a standalone collection.
        """
        if is_cluster and tower_module == 'project_manual':
            pytest.skip(
                'Manual projects are discouraged in general, specially on cluster deployments.'
            )

        virtual_env_path = venv_path(python_venv['name'])

        extra_vars = {
            'tower_module_under_test': tower_module,
            'ansible_python_interpreter': os.path.join(virtual_env_path, 'bin/python'),
            'collection_id': collection_fqcn
        }
        jt = factories.job_template(project=project, playbook='tower_modules/wrapper.yml',
                                    extra_vars=json.dumps(extra_vars), verbosity=5)
        jt.add_credential(tower_credential)
        jt.custom_virtualenv = virtual_env_path
        job = jt.launch().wait_until_completed()

        job.assert_successful()
