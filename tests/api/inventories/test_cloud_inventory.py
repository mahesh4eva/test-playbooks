import json
import threading
from pprint import pformat

import pytest

from awxkit.config import config

from tests.api import APITest


@pytest.mark.usefixtures('authtoken')
class TestCloudInventoryUpdate(APITest):

    def test_cloud_update_with_source_region(self, region_choices, cloud_inventory_source_supporting_source_regions):
        """Assess inventory imports with all possible choices for source_regions.

        Note: we expect inventory imports with certain regions to fail. For more context,
        please see https://github.com/ansible/ansible-tower/issues/545.
        """
        inv_source_pg = cloud_inventory_source_supporting_source_regions
        # provide list of values for source_regions given each provider
        cloud_provider = inv_source_pg.source
        if cloud_provider == 'ec2':
            source_regions = region_choices['ec2']
        elif cloud_provider == 'azure_rm':
            source_regions = region_choices['azure']
        elif cloud_provider == 'gce':
            source_regions = region_choices['gce']
        else:
            raise NotImplementedError("Unexpected cloud_provider: %s." % cloud_provider)
        unsupported_source_regions = ['cn-north-1', 'us-gov-west-1', 'LON']

        for source_region in source_regions:
            # patch inv_source_pg and launch update
            inv_source_pg = cloud_inventory_source_supporting_source_regions
            inv_source_pg.patch(source_regions=source_region)
            assert inv_source_pg.source_regions.lower() == source_region.lower(), \
                "Unexpected value for inv_source_pg.source_regions after patching the inv_source_pg with %s." % source_region
            update_pg = inv_source_pg.update().wait_until_completed()

            # assert that the update was successful if used with supported source region
            if source_region not in unsupported_source_regions:
                update_pg.assert_successful()
                inv_source_pg.get().assert_successful()

            # assert that update fails if used with unsupported source region
            else:
                assert update_pg.status == "failed", \
                    "inventory_update %s did not fail with unsupported region %s." % (update_pg, source_region)
                assert inv_source_pg.get().status == "failed", \
                    "An inventory_update failed, but the inventory_source did not fail - %s" % inv_source_pg

            # TODO: Assert specific cloud instance is now listed in group

    def _parallel_run_updates(self, inventory_sources):
        updates = []
        for inv_source in inventory_sources:
            updates.append(inv_source.update())

        threads = [threading.Thread(target=update.wait_until_completed, args=()) for update in updates]
        [t.start() for t in threads]
        [t.join() for t in threads]

        for inv_source in inventory_sources:
            # need to update objects so they have reference to last update
            inv_source = inv_source.get()

    @pytest.fixture
    def _cloud_inventory_source_with_unpopulated_region(self, request):
        source_to_region = {
            'aws': 'sa-east-1',
            'azure': 'japanwest',
            'gce': 'asia-east1-c',
            }
        source_to_inv_source = {}
        for source, region in source_to_region.items():
            source_to_inv_source[source] = request.getfixturevalue(source + '_inventory_source')
            source_to_inv_source[source].patch(source_regions=region)

        self._parallel_run_updates(source_to_inv_source.values())
        return source_to_inv_source

    @pytest.fixture(params=['aws', 'azure', 'gce'], ids=['aws', 'azure', 'gce'])
    def cloud_inventory_source_unpopulated_region(self, request, _cloud_inventory_source_with_unpopulated_region):
        return _cloud_inventory_source_with_unpopulated_region[request.param]

    @pytest.fixture
    def _cloud_inventory_source_with_populated_region(self, request):
        source_to_region = {
            'aws': 'us-east-1',
            'azure': 'eastus',
            'gce': 'all',
            }
        source_to_inv_source = {}
        for source, region in source_to_region.items():
            source_to_inv_source[source] = request.getfixturevalue(source + '_inventory_source')
            source_to_inv_source[source].patch(source_regions=region)

        self._parallel_run_updates(source_to_inv_source.values())
        return source_to_inv_source

    @pytest.fixture(params=['aws', 'azure', 'gce'], ids=['aws', 'azure', 'gce'])
    def cloud_inventory_source_populated_region(self, request, _cloud_inventory_source_with_populated_region):
        return _cloud_inventory_source_with_populated_region[request.param]

    def test_cloud_update_with_populated_source_region(self, cloud_inventory_source_populated_region):
        """Tests that hosts are imported when applying source regions containing hosts.

        NOTE: test may fail if our expected test hosts are down.
        """
        # TODO: Once we populate all regions with an instance, don't think we'll need a test
        # tailored to a subset of regions with instances.

        inv_source = cloud_inventory_source_populated_region
        inv_update = inv_source.related.last_update.get()

        # assert that the update was successful
        inv_update.assert_successful()
        inv_source.get().assert_successful()

        # assert that hosts were imported
        hosts_imported = inv_source.related.inventory.get().total_hosts
        assert hosts_imported > 0, f"Expected there to be hosts in this region! Found {hosts_imported} instead."

    @pytest.mark.ansible_integration
    def test_cloud_update_with_unpopulated_source_region(self, cloud_inventory_source_unpopulated_region):
        """Tests that hosts are not imported when applying source regions not containing hosts.

        NOTE: test may fail if someone spins up an instance in one of these regions. Regions correspond as follow:
        * sa-east-1    => South America (Sao Paulo)
        * HKG          => Hong Kong
        * West_Japan   => Japan West
        * asia-east1-c => Asia East (C)
        """
        inv_source = cloud_inventory_source_unpopulated_region
        inv_update = inv_source.related.last_update.get()
        inv_update.assert_successful()

        # assert that no hosts were imported
        hosts_imported = inv_source.related.inventory.get().total_hosts
        assert hosts_imported == 0, f"Unexpected number of hosts returned ({hosts_imported} != 0)."

    @pytest.mark.parametrize("instance_filter", ["tag-key=Name", "key-name=jenkins", "tag:Name=*"])
    @pytest.mark.ansible_integration
    def test_update_with_matched_aws_instance_filter(self, factories, instance_filter, aws_credential):
        """Tests inventory imports with matched AWS instance filters. NOTE: test may fail
        if our expected test hosts are down.
        """
        aws_inventory_source = factories.inventory_source(source='ec2', instance_filters=instance_filter, credential=aws_credential)
        update = aws_inventory_source.update().wait_until_completed()
        update.assert_successful()
        aws_inventory_source.get().assert_successful()

        assert aws_inventory_source.ds.inventory.related.hosts.get().count > 0

    @pytest.mark.parametrize("instance_filter", ["tag-key=UNMATCHED", "key-name=UNMATCHED", "tag:Name=UNMATCHED"])
    @pytest.mark.ansible_integration
    def test_update_with_unmatched_aws_instance_filter(self, aws_inventory_source, instance_filter):
        """Tests inventory imports with unmatched AWS instance filters

        NOTE: test may fail if someone spins up an unexpected instance.
        """
        # patch the inv_source_pg and launch the update
        inv_source_pg = aws_inventory_source
        inventory = aws_inventory_source.related.inventory.get()
        inv_source_pg.patch(instance_filters=instance_filter)
        update_pg = inv_source_pg.update().wait_until_completed()

        # assert that the update was successful
        update_pg.assert_successful()
        inv_source_pg.get().assert_successful()

        # assert whether hosts were imported
        hosts_imported = inventory.get().total_hosts
        assert hosts_imported == 0, f"Unexpected number of hosts returned ({hosts_imported} != 0)."

    @pytest.mark.ansible_integration
    @pytest.mark.parametrize("only_group_by, expected_group_names",
                             [("", ["accounts", "ec2", "images", "instance_states", "keys", "platforms", "regions",
                                    "security_groups", "tags", "types", "vpcs", "zones"],),
                              ("availability_zone", ["ec2", "zones"],),
                              ("ami_id", ["ec2", "images"],),
                              ("instance_id", ["ec2", "instances"],),
                              ("instance_type", ["ec2", "types"],),
                              ("key_pair", ["ec2", "keys"],),
                              ("region", ["ec2", "regions"],),
                              ("security_group", ["ec2", "security_groups"],),
                              ("availability_zone,ami_id", ["ec2", "zones", "images"],),
                              ("platform", ["ec2", "platforms"],)],
                             ids=['""', "availability_zone", "ami_id", "instance_id", "instance_type", "key_pair",
                                  "region", "security_group", "availability_zone,ami_id", "platform"])
    def test_aws_update_with_only_group_by(self, aws_inventory_source, only_group_by, expected_group_names):
        """Tests that expected groups are created when supplying value for only_group_by."""
        inv_source = aws_inventory_source
        inventory = aws_inventory_source.related.inventory.get()
        inv_source.compatibility_mode = True
        inv_source.group_by = only_group_by

        update = inv_source.update().wait_until_completed()
        update.assert_successful()
        inv_source.get().assert_successful()

        groups = inventory.related.root_groups.get()
        actual_group_names = set([group.name for group in groups.results])
        # extra group name returned by the plugin
        if 'aws_ec2' in actual_group_names:
            actual_group_names.remove('aws_ec2')
        assert actual_group_names == set(expected_group_names)

        # confirm desired auth env vars are in update context
        assert 'AWS_ACCESS_KEY_ID' in update.job_env
        assert 'AWS_SECRET_ACCESS_KEY' in update.job_env

    @pytest.mark.ansible_integration
    @pytest.mark.parametrize("only_group_by", [None, 'location', 'os_family', 'resource_group', 'security_group'])
    def test_azure_update_with_only_group_by(self, factories, only_group_by):
        """Azure does not support group_by, but will apply options if given."""
        group_by_dict = {
            "group_by_resource_group": False,
            "group_by_location": False,
            "group_by_security_group": False,
            "group_by_tag": False,
            "group_by_os_family": False
        }
        if only_group_by:
            group_by_dict['group_by_{}'.format(only_group_by)] = True
        inv_source = factories.inventory_source(
            source='azure_rm',
            credential=factories.credential(kind='azure_rm'),
            source_vars=json.dumps(group_by_dict)
        )

        update = inv_source.update().wait_until_completed()
        update.assert_successful()

        groups = inv_source.get_related('groups', parents__isnull=True).results  # root groups
        actual_group_names = set(group.name for group in groups)

        if only_group_by == 'location':
            actual_group_names.remove('azure')
            for group_name in actual_group_names:
                assert 'us' in group_name  # assuming all servers are in USA...
        elif only_group_by == 'os_family':
            assert actual_group_names == set(['azure', 'linux'])  # assuming no windows servers running
        elif only_group_by == 'resource_group':
            # potentially flaky if Azure resources are modified
            assert set(['azure', 'demo-dj', 'qe']).issubset(actual_group_names)  # Azure users could change
        elif only_group_by == 'security_group':
            assert 'towerqe-nsg' in actual_group_names
        else:
            assert actual_group_names == set(['azure'])

    def test_azure_use_private_ip(self, factories, ansible_version_cmp):
        source_vars = {"use_private_ip": True}
        inv_source = factories.inventory_source(
            source='azure_rm',
            credential=factories.credential(kind='azure_rm'),
            source_vars=json.dumps(source_vars)
        )

        update = inv_source.update().wait_until_completed()
        update.assert_successful()

        host_results = inv_source.get_related('hosts')
        assert host_results.count > 0  # this did an unfiltered import, so this should not fail
        for host in host_results.results:
            if (ansible_version_cmp('2.8.0') < 0) and host.name == 'demo-dj':
                # Fix for bug was merged into 2.8 https://github.com/ansible/ansible/pull/54099
                # Bug in previous ansible versions caused host with same name as group to have hostvars stolen
                continue
            hostvars = host.variables
            priv_ip = hostvars.get('private_ip', 'NO KEY private_ip FOUND')
            ansible_host = hostvars.get('ansible_host', 'NO KEY ansible_host FOUND')
            # normally this is the public IP, not the private IP
            assert priv_ip == ansible_host, 'private_ip and ansible host do not match!\n' \
                f'the source var to customize the anisble host was not respected! {priv_ip} != {ansible_host}\n' \
                f' All host vars were as follows {pformat(hostvars)}'

    def test_azure_use_resource_group_filters(self, skip_if_pre_ansible28, factories, ansible_version_cmp):
        # Fix for bug was merged into 2.8 https://github.com/ansible/ansible/pull/54099
        # Bug in previous ansible versions caused host with same name as group to have hostvars stolen
        res_group = "demo-dj"
        source_vars = {"resource_groups": res_group}
        inv_source = factories.inventory_source(
            source='azure_rm',
            credential=factories.credential(kind='azure_rm'),
            source_vars=json.dumps(source_vars)
        )

        update = inv_source.update().wait_until_completed()
        update.assert_successful()

        host_results = inv_source.get_related('hosts')
        assert host_results.count > 0  # test could be failing because account changed content
        for host in host_results.results:
            hostvars = host.variables
            found_res_group = hostvars.get('resource_group', 'NO KEY resource_group FOUND')
            assert found_res_group == res_group, f'Resource group {res_group} not found, only found \n {found_res_group}. All hostvars found were {pformat(hostvars)}'

    @pytest.mark.parametrize("tags", ['Creator,peanutbutter',
                                      'Creator:jmarshall,peanutbutter:jelly'])
    def test_azure_use_tags_filters(self, factories, tags):
        # tags can be a list of keys or key:value pairs
        # the filtering uses AND operation -- a host must have each key
        # or key:value in its tags dictionary, else it is excluded
        #
        # In tower interface, spaces are allowed in the input, e.g.
        # tags: Creator, peanutbutter
        # inventory.py strips the extra spaces
        # awxkit does not strip, and expects proper JSON-able content and
        # will throw an error if spaces are present
        source_vars = "tags: " + tags

        inv_source = factories.inventory_source(
            source='azure_rm',
            credential=factories.credential(kind='azure_rm'),
            source_vars=source_vars
        )

        update = inv_source.update().wait_until_completed()
        update.assert_successful()

        host_results = inv_source.get_related('hosts')

        assert host_results.count > 0

        tags_list = []
        tags_dict = {}
        if ':' in tags:
            # tags is a dictionary
            for kv in tags.split(','):
                kvpair = kv.split(':')
                tags_dict[kvpair[0].strip()] = kvpair[1].strip()
        else:
            # tags is a list of keys
            tags_list = [i.strip() for i in tags.split(',')]

        for host in host_results.results:
            hostvars = host.variables
            host_tags = hostvars.get('tags', {})
            for kv in tags_dict: # check for matching kv pairs
                assert tags_dict[kv] == host_tags.get(kv)
            for kv in tags_list: # check for matching keys
                assert kv in host_tags

    @pytest.mark.ansible_integration
    def test_aws_replace_dash_in_groups_source_variable(self, factories):
        """Tests that AWS inventory groups will be registered with underscores instead of hyphens
        when using "replace_dash_in_groups" source variable
        """
        inv_source = factories.inventory_source(
            source='ec2',
            source_regions='us-east-1',  # region where the flag is located, to reduce import size
            group_by='tag_keys',  # assure the tag groups are returned in all cases
            credential=factories.credential(kind='aws'),
            source_vars=json.dumps(dict(replace_dash_in_groups=True))
        )

        # Update and assert that the inventory_update is marked as successful
        inv_update = inv_source.update().wait_until_completed()
        inv_update.assert_successful()

        # Assert that hyphen containing tag groups are registered with underscores
        flag_like_group_names = set(
            group.name for group in inv_source.get_related('groups', name__icontains='flag').results
        )
        assert flag_like_group_names, 'Inventory update produced no group corresponding to expected tag'
        for group_name in ['tag_Test_Flag_2202', 'tag_Test_Flag_2202_Replace_Dash_In_Groups']:
            assert group_name in flag_like_group_names, (
                'An inventory sync was launched with "replace_dash_in_groups: true", '
                'but desired group with sanitized tag "{0}" not found.'.format(group_name))

    @pytest.mark.parametrize('inventory_source', ['azure_rm', None], ids=['azure', 'custom'])
    def test_environment_variables_sourced_with_inventory_update_with_azure_credential(self, factories, inventory_source):
        azure_cred = factories.credential(kind='azure_rm', client='SomeClient', cloud_environment='SomeCloudEnvironment',
                                             password='SomePassword', secret='SomeSecret', subscription='SomeSubscription',
                                             tenant='SomeTenant', username='SomeUsername')
        if inventory_source:
            azure = factories.inventory_source(credential=azure_cred, inventory_source=inventory_source)
        else:
            # custom inventory script created when no inventory_source specified
            azure = factories.inventory_source(credential=azure_cred)
        update = azure.update().wait_until_completed()
        job_env = update.job_env
        assert job_env.AZURE_CLIENT_ID == 'SomeClient'
        assert job_env.AZURE_CLOUD_ENVIRONMENT == 'SomeCloudEnvironment'
        assert job_env.AZURE_SECRET == '**********'
        assert job_env.AZURE_SUBSCRIPTION_ID == 'SomeSubscription'
        assert job_env.AZURE_TENANT == 'SomeTenant'

    def test_tower_inventory_incorrect_password(self, ansible_version_cmp, factories):
        tower_cred = factories.credential(
            kind='tower',
            inputs={
                'host': config.base_url,
                'username': config.credentials.users.admin.username,
            'password': 'INVALID!',
            'verify_ssl': False
        }
    )
        tower_source = factories.inventory_source(
            source='tower', credential=tower_cred,
            instance_filters='123',
        )
        inv_update = tower_source.update().wait_until_completed()
        assert inv_update.status == 'failed'
        if ansible_version_cmp('2.8.0') < 0:
            inv_update.assert_text_in_stdout('Failed to validate the license')
        else:
            inv_update.assert_text_in_stdout('HTTP Error 401: Unauthorized')

    @pytest.mark.parametrize('hostname, error', [
        ['https://###/', ('Invalid URL', 'error no host given')],
        ['example.org', ('Failed to validate the license', 'HTTP Error 404')],
    ])
    def test_tower_inventory_sync_failure_has_descriptive_error_message(self, ansible_version_cmp, factories, hostname, error):
        if ansible_version_cmp('2.8.0') < 0:
            error = error[0]
        else:
            error = error[1]
        tower_cred = factories.credential(kind='tower', inputs={
            'host': hostname,
            'username': 'x',
            'password': 'y'
        })
        tower_source = factories.inventory_source(
            source='tower', credential=tower_cred,
            instance_filters='123'
        )
        inv_update = tower_source.update().wait_until_completed()
        assert inv_update.status == 'failed'
        inv_update.assert_text_in_stdout(error)
