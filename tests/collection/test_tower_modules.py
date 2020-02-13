from awxkit.config import config
from awxkit import utils

from copy import deepcopy
import pytest

from tests.api import APITest
from tests.collection import CUSTOM_VENVS, CUSTOM_VENVS_NAMES

TEST_REPO_URL = "https://github.com/ansible/test-playbooks.git"


# FIXME Remove "skip_if_cluster" fixture. We must skip if cluster right now
# because the node we're installing awx collection on doesn't have access to
# the tower repo in a cluster deployment.
@pytest.mark.fixture_args(venvs=CUSTOM_VENVS, cluster=True, venv_group='local')
@pytest.mark.usefixtures('skip_if_pre_ansible29', 'skip_if_openshift', 'authtoken', 'skip_if_cluster', 'skip_if_wrong_python')
@pytest.mark.parametrize('python_venv', CUSTOM_VENVS, ids=CUSTOM_VENVS_NAMES)
class Test_Ansible_Tower_Modules(APITest):
    def run_module(self, venv_path, ansible_adhoc, is_docker, request, module_name, module_args=None):
        if module_args is None:
            module_args = {}

        ansible_adhoc = ansible_adhoc()
        # If we're not in the docker deployment, we must change the hosts in
        # the venv_group to use the right virtualenv that has the dependencies
        # for awx collection
        fixture_args = request.node.get_closest_marker('fixture_args')
        venv_group = fixture_args.kwargs.get('venv_group')
        if not is_docker:
            for host in ansible_adhoc.options['inventory_manager'].groups[venv_group].hosts:
                host.vars['ansible_python_interpreter'] = venv_path + 'bin/python'

        module_output = getattr(ansible_adhoc[venv_group], module_name)(
                **module_args,
                tower_username=config.credentials.default.username,
                tower_password=config.credentials.default.password,
                tower_host=config.base_url,
                validate_certs=False,
            )

        for hostname in ansible_adhoc.options['inventory_manager'].groups[venv_group].host_names:
            assert hasattr(module_output, 'contacted'), f'module execution failed: {module_output.__dict__}'
            assert hostname in module_output.contacted, f'module could not contact localhost: {module_output.__dict__}'
            if 'exception' in module_output.contacted[hostname]:
                pytest.fail(f'module threw an exception: {module_output.__dict__}')
            assert 'invocation' in module_output.contacted[hostname], f'module could not be invoked: {module_output.__dict__}'

        return module_output

    def check_module_output(self, request, ansible_adhoc, module_output, module_args=None, changed=None):
        if not module_args:
            module_args = {}

        ansible_adhoc = ansible_adhoc()
        fixture_args = request.node.get_closest_marker('fixture_args')
        venv_group = fixture_args.kwargs.get('venv_group')

        # Make sure there is at least 1 host we are checking
        assert ansible_adhoc.options['inventory_manager'].groups[venv_group].host_names

        for hostname in ansible_adhoc.options['inventory_manager'].groups[venv_group].host_names:
            assert 'module_args' in module_output.contacted[hostname]['invocation'], f'module arguments missing: {module_output.__dict__}'
            for (k, v) in module_args.items():
                assert k in module_output.contacted[hostname]['invocation']['module_args'], f'module argument missing: {k}, full module_output: {module_output.__dict__}'
                actual_value = module_output.contacted[hostname]['invocation']['module_args'][k]
                assert v == actual_value, f'module argument has wrong value on output, key: {k}, value: {v}, expected value: {actual_value}, full module_output: {module_output.__dict__}'
            if changed is not None:
                assert 'changed' in module_output.contacted[hostname], f'module_output has no changed attribute: {module_output.__dict__}'
                actual_changed = module_output.contacted[hostname]['changed']
                assert changed == actual_changed, f'module_output incorrect changed value, expected changed: {changed} actual state: {actual_changed}'

    def test_ansible_tower_module_organization_create_update(self, factories, venv_path, ansible_collections_path, request, update_setting_pg, v2, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        org_name = utils.random_title()
        request.addfinalizer(lambda *args: v2.organizations.get(name=org_name).results[0].delete())
        module_args = {
            'name': org_name,
            'description': 'hello world',
        }

        module_output = self.run_module(venv_path(python_venv['name']),
                ansible_adhoc, is_docker, request, collection_fqcn + '.tower_organization', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        org = v2.organizations.get(name=org_name).results.pop()
        org_id = org.id
        assert org_name == org['name']
        assert org['description'] == 'hello world'

        # Test updating the object
        module_args = {
            'name': org_name,
            'description': 'updated description',
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_organization', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        org = v2.organizations.get(name=org_name).results.pop()
        assert org.id == org_id
        assert org_name == org['name']
        assert org['description'] == 'updated description'

    def test_ansible_tower_module_organization_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        org = factories.organization()
        module_args = {
            'name': org.name,
            'state': 'absent',
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_organization', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.organizations.get(name=org.name).results, interval=1, timeout=30)
        assert not v2.organizations.get(name=org.name).results

    def test_ansible_tower_module_organization_check_mode(self, factories, tower_version, venv_path, is_docker, v2, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        '''
        Ensure that orgnization check_mode: True returns the tower_version
        '''
        pytest.skip("unimplemented")

    def test_ansible_tower_module_project_create_update(self, request, ansible_collections_path, v2, factories, venv_path, organization, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        proj_name = utils.random_title()
        request.addfinalizer(lambda *args: v2.projects.get(name=proj_name).results[0].delete())

        module_args = {
            'name': proj_name,
            'description': 'hello world',
            'scm_type': 'git',
            'scm_url': TEST_REPO_URL,
            'organization': organization.name,
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_project', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        proj = v2.projects.get(name=proj_name).results[0]
        proj_id = proj.id
        proj.related.project_updates.get().results[0].wait_until_completed()
        assert proj_name == proj['name']
        assert proj['description'] == 'hello world'
        assert proj['scm_type'] == 'git'
        assert proj['scm_url'] == TEST_REPO_URL
        assert proj['organization'] == organization.id

        module_args['description'] = 'updated description'

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_project', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        proj = v2.projects.get(name=proj_name).results[0]
        proj.related.project_updates.get().results[0].wait_until_completed()
        assert proj.id == proj_id
        assert proj_name == proj['name']
        assert proj['description'] == 'updated description'
        assert proj['scm_type'] == 'git'
        assert proj['scm_url'] == TEST_REPO_URL
        assert proj['organization'] == organization.id

    def test_ansible_tower_module_project_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        proj = factories.project()
        module_args = {
            'name': proj.name,
            'organization': proj.summary_fields.organization.name,
            'state': 'absent',
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_project', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.projects.get(name=proj.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_credential_create_update(self, request, ansible_collections_path, v2, factories, venv_path, organization, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        cred_name = utils.random_title()
        request.addfinalizer(lambda *args: v2.credentials.get(name=cred_name).results[0].delete())

        module_args = {
            'name': cred_name,
            'description': 'hello world',
            'kind': 'ssh',
            'organization': organization.name,
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_credential', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        cred = v2.credentials.get(name=cred_name).results.pop()
        cred_id = cred.id
        assert cred_name == cred['name']
        assert cred['description'] == 'hello world'
        assert cred['kind'] == 'ssh'
        assert cred['organization'] == organization.id

        module_args['description'] = 'updated description'

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_credential', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        cred = v2.credentials.get(name=cred_name).results.pop()
        assert cred_id == cred.id
        assert cred_name == cred['name']
        assert cred['description'] == 'updated description'
        assert cred['kind'] == 'ssh'
        assert cred['organization'] == organization.id

    def test_ansible_tower_module_credential_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        cred = factories.credential()
        module_args = {
            'name': cred.name,
            'state': 'absent',
            'kind': cred.kind,
            'organization': cred.summary_fields.organization.name
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_credential', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.credentials.get(name=cred.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_credential_type_create_update(self, request, ansible_collections_path, v2, factories, venv_path, organization, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        cred_name = utils.random_title()
        request.addfinalizer(lambda *args: v2.credential_types.get(name=cred_name).results[0].delete())
        module_args = {
            'name': cred_name,
            'description': 'hello world',
            'kind': 'cloud',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_credential_type', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        cred = v2.credential_types.get(name=cred_name).results.pop()
        cred_id = cred.id
        assert cred_name == cred['name']
        assert cred['description'] == 'hello world'
        assert cred['kind'] == 'cloud'

        module_args['description'] = 'updated description'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_credential_type', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        cred = v2.credential_types.get(name=cred_name).results.pop()
        assert cred.id == cred_id
        assert cred_name == cred['name']
        assert cred['description'] == 'updated description'
        assert cred['kind'] == 'cloud'

    def test_ansible_tower_module_credential_type_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        cred = factories.credential_type()
        module_args = {
            'name': cred.name,
            'state': 'absent',
            'kind': cred.kind,
        }

        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_credential_type', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.credential_types.get(name=cred.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_notification_create_update(self, request, ansible_collections_path, v2, factories, venv_path, organization, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        notification_name = utils.random_title()
        request.addfinalizer(lambda *args: v2.notification_templates.get(name=notification_name).results[0].delete())
        module_args = {
            'name': notification_name,
            'organization': organization.name,
            'description': 'hello world',
            'channels': ['#foo'],
            'notification_type': 'slack',
            'token': 'fake_token',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_notification', module_args)
        # TODO (calebb): find a way to check this parameter that makes sense
        modified_module_args = deepcopy(module_args)
        modified_module_args.pop('token')
        self.check_module_output(request, ansible_adhoc, module_output, modified_module_args, True)

        notification = v2.notification_templates.get(name=notification_name).results.pop()
        notification_id = notification.id
        assert notification_name == notification['name']
        assert notification['description'] == 'hello world'
        assert notification.summary_fields.organization.name == organization.name
        assert notification['notification_type'] == 'slack'

        module_args['description'] = 'updated description'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_notification', module_args)
        # TODO (calebb): find a way to check this parameter that makes sense
        modified_module_args = deepcopy(module_args)
        modified_module_args.pop('token')
        self.check_module_output(request, ansible_adhoc, module_output, modified_module_args, True)

        notification = v2.notification_templates.get(name=notification_name).results.pop()
        assert notification.id == notification_id
        assert notification_name == notification['name']
        assert notification['description'] == 'updated description'
        assert notification.summary_fields.organization.name == organization.name
        assert notification['notification_type'] == 'slack'

    def test_ansible_tower_module_notification_delete(self, v2, factories, venv_path, organization, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        token = utils.random_title()
        notification = factories.notification_template(token=token)
        module_args = {
            'name': notification.name,
            'organization': notification.summary_fields.organization.name,
            'channels': notification.notification_configuration.channels,
            'notification_type': notification.notification_type,
            'token': token,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_notification', module_args)
        # TODO (calebb): find a way to check this parameter that makes sense
        modified_module_args = deepcopy(module_args)
        modified_module_args.pop('token')
        self.check_module_output(request, ansible_adhoc, module_output, modified_module_args, True)

        utils.poll_until(lambda: not v2.notification_templates.get(name=notification.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_group_create_update(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        group_name = utils.random_title()
        inv = factories.inventory()
        request.addfinalizer(lambda *args: v2.groups.get(name=group_name).results[0].delete())
        module_args = {
            'name': group_name,
            'description': 'hello world',
            'inventory': inv.name
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_group', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        group = v2.groups.get(name=group_name).results.pop()
        group_id = group.id
        assert group_name == group['name']
        assert group['description'] == 'hello world'
        assert group['inventory'] == inv.id

        module_args['description'] = 'updated description'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_group', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        group = v2.groups.get(name=group_name).results.pop()
        assert group.id == group_id
        assert group_name == group['name']
        assert group['description'] == 'updated description'
        assert group['inventory'] == inv.id

    def test_ansible_tower_module_group_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        group = factories.group()
        module_args = {
            'name': group.name,
            'inventory': group.summary_fields.inventory.name,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_group', module_args)
        # TODO (calebb): This parameter should probably be output by the collection when we replace tower-cli
        modified_module_args = deepcopy(module_args)
        modified_module_args.pop('state')
        self.check_module_output(request, ansible_adhoc, module_output, modified_module_args, True)

        utils.poll_until(lambda: not v2.groups.get(name=group.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_host_create_update(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        host_name = utils.random_title()
        inv = factories.inventory()
        request.addfinalizer(lambda *args: v2.hosts.get(name=host_name).results[0].delete())
        module_args = {
            'name': host_name,
            'description': 'hello world',
            'inventory': inv.name
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_host', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        host = v2.hosts.get(name=host_name).results.pop()
        host_id = host.id
        assert host_name == host['name']
        assert host['description'] == 'hello world'
        assert host['inventory'] == inv.id

        module_args['description'] = 'updated description'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_host', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        host = v2.hosts.get(name=host_name).results.pop()
        assert host.id == host_id
        assert host_name == host['name']
        assert host['description'] == 'updated description'
        assert host['inventory'] == inv.id

    def test_ansible_tower_module_host_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        host = factories.host()
        module_args = {
            'name': host.name,
            'inventory': host.summary_fields.inventory.name,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_host', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.hosts.get(name=host.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_inventory_create_update(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        inventory_name = utils.random_title()
        org = factories.organization()
        request.addfinalizer(lambda *args: v2.inventory.get(name=inventory_name).results[0].delete())
        module_args = {
            'name': inventory_name,
            'description': 'hello world',
            'organization': org.name
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_inventory', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        inventory = v2.inventory.get(name=inventory_name).results.pop()
        inventory_id = inventory.id
        assert inventory_name == inventory['name']
        assert inventory['description'] == 'hello world'
        assert inventory['organization'] == org.id

        module_args['description'] = 'updated description'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_inventory', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        inventory = v2.inventory.get(name=inventory_name).results.pop()
        assert inventory_id == inventory.id
        assert inventory_name == inventory['name']
        assert inventory['description'] == 'updated description'
        assert inventory['organization'] == org.id

    def test_ansible_tower_module_inventory_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        inventory = factories.inventory()
        module_args = {
            'name': inventory.name,
            'organization': inventory.summary_fields.organization.name,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_inventory', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.inventory.get(name=inventory.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_inventory_source_create_update(self, request, ansible_collections_path, factories, v2, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        inventory_source_name = utils.random_title()
        org = factories.organization()
        inventory_script = factories.inventory_script(organization=org)
        inventory = factories.inventory(organization=org)
        request.addfinalizer(lambda *args: v2.inventory_sources.get(name=inventory_source_name).results[0].delete())
        module_args = {
            'name': inventory_source_name,
            'inventory': inventory.name,
            'description': 'hello world',
            'source': 'custom',
            'source_script': inventory_script.name,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_inventory_source', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        inventory_source = v2.inventory_sources.get(name=inventory_source_name).results.pop()
        inventory_source_id = inventory_source.id
        assert inventory_source_name == inventory_source['name']
        assert inventory_source['description'] == 'hello world'

        module_args['description'] = 'updated description'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_inventory_source', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        inventory_source = v2.inventory_sources.get(name=inventory_source_name).results.pop()
        assert inventory_source_id == inventory_source.id
        assert inventory_source_name == inventory_source['name']
        assert inventory_source['description'] == 'updated description'

    def test_ansible_tower_module_inventory_source_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        inventory_source = factories.inventory_source()
        module_args = {
            'name': inventory_source.name,
            'inventory': inventory_source.summary_fields.inventory.name,
            'source': inventory_source.source,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_inventory_source', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.inventory_sources.get(name=inventory_source.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_job(self, request, ansible_collections_path, factories, v2, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        jt_name = utils.random_title()
        vault_cred = factories.credential(kind='vault', inputs=dict(vault_password='fake'))
        project = factories.project()
        inventory = factories.inventory()
        factories.host(inventory=inventory, variables=dict(ansible_host='localhost', ansible_connection='local'))

        # We need this to teardown the JT if it fails before the end. The try
        # block also means it wont fail if we get to the end and clean up the
        # JT as part of the test
        def cleanup_jt():
            try:
                return v2.job_templates.get(name=jt_name).results[0].delete()
            except:
                print("failed to remove JT in teardown")

        # Create a JT
        request.addfinalizer(cleanup_jt)
        jt_module_args = {
            'name': jt_name,
            'description': 'hello world',
            'job_type': 'run',
            'inventory': inventory.name,
            'playbook': 'sleep.yml',
            'project': project.name,
            'vault_credential': vault_cred.name,
            'extra_vars': {'sleep_interval': 120},
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_template', jt_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, jt_module_args, True)

        jt = v2.job_templates.get(name=jt_name).results.pop()
        jt_id = jt.id
        assert jt_name == jt['name']
        assert jt['description'] == 'hello world'
        assert jt['job_type'] == 'run'
        assert jt['inventory'] == inventory.id
        assert jt['playbook'] == 'sleep.yml'
        assert jt['project'] == project.id
        assert jt['extra_vars'] == '{"sleep_interval": 120}'

        jt_cred = jt['related']['credentials'].get()['results']

        assert len(jt_cred) == 1
        assert jt_cred[0]['id'] == vault_cred.id
        assert jt_cred[0]['name'] == vault_cred.name
        assert jt_cred[0]['kind'] == 'vault'

        # Launch the JT we just built
        job_module_args = {
            'job_template': jt_name,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_launch', job_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, job_module_args, True)

        job = v2.jobs.get(name=jt_name).results.pop()
        assert job.summary_fields.job_template.name == jt_name

        job_id1 = job.id

        # Cancel the job we just launched
        job_module_args = {
            'job_id': job_id1,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_cancel', job_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, job_module_args, True)

        utils.poll_until(lambda: v2.jobs.get(id=job_id1).results.pop().status == "canceled", interval=1, timeout=300)

        # Update the JT
        jt_module_args['description'] = 'updated description'
        jt_module_args['extra_vars'] = {'sleep_interval': 5}
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_template', jt_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, jt_module_args, True)

        jt = v2.job_templates.get(name=jt_name).results.pop()
        assert jt.id == jt_id
        assert jt_name == jt['name']
        assert jt['description'] == 'updated description'
        assert jt['job_type'] == 'run'
        assert jt['inventory'] == inventory.id
        assert jt['playbook'] == 'sleep.yml'
        assert jt['project'] == project.id
        assert jt['extra_vars'] == '{"sleep_interval": 5}'

        jt_cred = jt['related']['credentials'].get()['results']

        assert len(jt_cred) == 1
        assert jt_cred[0]['id'] == vault_cred.id
        assert jt_cred[0]['name'] == vault_cred.name
        assert jt_cred[0]['kind'] == 'vault'

        # Launch another job
        job_module_args = {
            'job_template': jt_name,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_launch', job_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, job_module_args, True)

        job = v2.jobs.get(name=jt_name).results[1]
        assert job.summary_fields.job_template.name == jt_name

        job_id2 = job.id

        # Sanity check
        assert job_id1 != job_id2

        # Wait for the job we just launched
        job_module_args = {
            'job_id': job_id2,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_wait', job_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, job_module_args, False)

        job = v2.jobs.get(id=job_id2).results.pop()
        assert job.summary_fields.job_template.name == jt_name
        job.assert_status("successful")

        # List jobs
        # I'm not entirely sure how to test this better
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_list')
        self.check_module_output(request, ansible_adhoc, module_output, changed=False)

        # Remove our job template
        jt_module_args['state'] = 'absent'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_job_template', jt_module_args)
        # TODO (calebb): This parameter should probably be output by the collection when we replace tower-cli
        jt_modified_module_args = deepcopy(jt_module_args)
        jt_modified_module_args.pop('state')
        self.check_module_output(request, ansible_adhoc, module_output, jt_modified_module_args, True)

        utils.poll_until(lambda: not v2.job_templates.get(name=jt_name).results, interval=1, timeout=30)

    def test_ansible_tower_module_role_create(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        org = factories.organization()
        user = factories.user()
        module_args = {
            'user': user.username,
            'organization': org.name,
            'role': 'admin',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_role', module_args)
        # TODO (calebb): This parameter should probably be output by the collection when we replace tower-cli
        modified_module_args = deepcopy(module_args)
        modified_module_args.pop('role')
        self.check_module_output(request, ansible_adhoc, module_output, modified_module_args, True)

        role = v2.users.get(id=user.id)['results'][0]['related']['roles'].get().results.pop()
        assert str(org.id) in role['related']['organization']
        assert role['related']['users'].get()['results'][0]['id'] == user.id

    def test_ansible_tower_module_team_create(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        team_name = utils.random_title()
        org = factories.organization()
        request.addfinalizer(lambda *args: v2.teams.get(name=team_name).results[0].delete())
        module_args = {
            'name': team_name,
            'organization': org.name
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_team', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        team = v2.teams.get(name=team_name).results.pop()
        assert team_name == team['name']
        assert team['organization'] == org.id

    def test_ansible_tower_module_team_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        team = factories.team()
        module_args = {
            'name': team.name,
            'organization': team.summary_fields.organization.name,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_team', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.teams.get(name=team.name).results, interval=1, timeout=30)

    def test_ansible_tower_module_user_create(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        username = utils.random_title(non_ascii=False)
        request.addfinalizer(lambda *args: v2.users.get(username=username).results[0].delete())
        module_args = {
            'username': username,
            'password': username,
            'email': 'example@example.com',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_user', module_args)
        # TODO (calebb): find a way to check this parameter that makes sense
        modified_module_args = deepcopy(module_args)
        modified_module_args.pop('username')
        modified_module_args.pop('password')
        self.check_module_output(request, ansible_adhoc, module_output, modified_module_args, True)

        user = v2.users.get(username=username).results.pop()
        assert username == user['username']
        assert user['email'] == 'example@example.com'

    def test_ansible_tower_module_user_delete(self, factories, v2, venv_path, is_docker, request, ansible_collections_path, ansible_adhoc, python_venv, collection_fqcn):
        user = factories.user()
        module_args = {
            'username': user.username,
            'email': user.email,
            'state': 'absent',
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_user', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        utils.poll_until(lambda: not v2.users.get(username=user.username).results, interval=1, timeout=30)

    def test_ansible_tower_module_label_create(self, request, ansible_collections_path, v2, factories, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        label_name = utils.random_title()
        org = factories.organization()
        module_args = {
            'name': label_name,
            'organization': org.name
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_label', module_args)
        self.check_module_output(request, ansible_adhoc, module_output, module_args, True)

        label = v2.labels.get(name=label_name).results.pop()
        assert label_name == label['name']

    def test_ansible_tower_module_workflow(self, request, ansible_collections_path, factories, v2, venv_path, is_docker, ansible_adhoc, python_venv, collection_fqcn):
        wf_name = utils.random_title()

        # We need this to teardown the WF if it fails before the end. The try
        # block also means it wont fail if we get to the end and clean up the
        # WF as part of the test
        def cleanup_wf():
            try:
                return v2.workflow_job_templates.get(name=wf_name).results[0].delete()
            except:
                print("failed to remove WF in teardown")

        request.addfinalizer(cleanup_wf)
        wfjt_module_args = {
            'name': wf_name,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_workflow_template', wfjt_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, wfjt_module_args, True)

        wf = v2.workflow_job_templates.get(name=wf_name).results.pop()
        assert wf_name == wf['name']

        # launch our workflow
        wf_module_args = {
            'workflow_template': wf_name,
        }
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_workflow_launch', wf_module_args)
        # TODO (calebb): This should probably report Changed: True, as we are
        # modifying the state of things, might be a thing to fix when we
        # replace the tower-cli
        self.check_module_output(request, ansible_adhoc, module_output, wf_module_args, False)

        wf_job = v2.workflow_jobs.get(name=wf_name).results.pop()
        assert wf_job['status'] == 'successful'
        assert wf_name == wf_job['name']

        # Remove our workflow
        wfjt_module_args['state'] = 'absent'
        module_output = self.run_module(venv_path(python_venv['name']), ansible_adhoc, is_docker, request, collection_fqcn + '.tower_workflow_template', wfjt_module_args)
        self.check_module_output(request, ansible_adhoc, module_output, wfjt_module_args, True)

        workflow_templates = v2.workflow_job_templates.get(name=wf_name).results
        assert not workflow_templates
