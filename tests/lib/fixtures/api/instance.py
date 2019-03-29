import pytest


@pytest.fixture
def active_instances(v2):
    """Returns instance list that excludes corner cases that tests should
    not normally run jobs against
    * no disabled instances
    * no lost instances
    * no isolated instances
    """
    return v2.instances.get(
        rampart_groups__controller__isnull=True,
        enabled=True,
        capacity__gt=0,
        page_size=200
    )


@pytest.fixture
def reset_instance(request):
    def func(instance):
        def teardown():
            instance.patch(capacity_adjustment=1, enabled=True, managed_by_policy=True)
        request.addfinalizer(teardown)
    return func


@pytest.fixture(params=[False, True], ids=['regular_tower_instance', 'isolated_node'])
def instance_group(request, authtoken, is_traditional_cluster, v2):
    """Return first the tower instance group, and then an isolated instance group.

    This is to enable running tests a second time on an isolated node if the platform
    under test is a traditional cluster and includes isolated nodes.
    """
    if request.param:
        if is_traditional_cluster:
            return v2.instance_groups.get(name='protected').results.pop()
        else:
            pytest.skip("Not on a cluster, cannot run on isolated node.")
    else:
        return v2.instance_groups.get(name='tower').results.pop()
