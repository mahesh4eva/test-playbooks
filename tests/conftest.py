"""Configuration for pytest plugins and fixtures"""
import os
import sys
import pkgutil
import pytest

from tests.lib.tower.license import generate_license
from tests.lib.license import apply_license_until_effective

# Add tests/lib directory to path
conftest_dir = os.path.dirname(__file__)
lib_dir = os.path.join(conftest_dir, 'lib')
if os.path.isdir(lib_dir):
    sys.path.insert(0, lib_dir)

import plugins  # NOQA
import plugins.pytest_restqa  # NOQA
import markers  # NOQA
import fixtures  # NOQA
import fixtures.api  # NOQA


# Load any plugins, fixtures and markers
def _pytest_plugins_generator(*extension_pkgs):
    # Finds all submodules in pytest extension packages and loads them
    found_plugins = set()
    for extension_pkg in extension_pkgs:
        path = extension_pkg.__path__
        prefix = f'{extension_pkg.__name__}.'
        for importer, modname, is_package in pkgutil.iter_modules(path, prefix):
            if not is_package:
                found_plugins.add(modname)
    return list(found_plugins)


# Automatically import plugins
pytest_plugins = _pytest_plugins_generator(fixtures, markers, plugins, fixtures.api)
# Manually add other plugins
pytest_plugins += [
    plugins.pytest_restqa.plugin.__name__,
    fixtures.api.__name__,
]


def pytest_addoption(parser):
    parser.addoption('--base-url',
                     action='store',
                     dest='base_url',
                     help='base url of tower instance under test')


@pytest.fixture(scope='session', autouse=True)
def session_install_enterprise_license_unlimited(session_authtoken, v2_session):
    """Apply an enterprise license to entire session when tests are run in the tests/ directory.

    Locate this fixture in tests/conftest.py such that it is applied when any session that includes
    the `tests` directory, this fixture automatically runs.

    **WARNING** the test suite located in tests/license overwrites this fixture because those tests
    meddle with the license in a different manner than every other test suite. One should never run
    tests in tests/license with any other sub-suite.
    """

    instance_count = 9223372036854775807
    days = 365

    # Fetch the current license information to restore later
    config = v2_session.get().config.get()
    license_info = generate_license(instance_count=instance_count, days=days, license_type='enterprise')
    license_info['eula_accepted'] = True
    if 'license_type' in config.license_info and 'instance_count' in config.license_info:
        if config.license_info.license_type == 'enterprise' and config.license_info.instance_count == instance_count:
            if not config.license_info.date_expired:
                # No need to apply license again, allready have a valid one that is sufficient for our needs
                return
    apply_license_until_effective(config, license_info)


def pytest_collection_modifyitems(items):
    """Modify tests related to `container_group` to run in serial."""
    for item in items:
        if "container_group" in (item.nodeid):
            item.add_marker(pytest.mark.serial)
