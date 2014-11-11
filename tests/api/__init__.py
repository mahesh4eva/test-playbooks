import pytest
import contextlib

@pytest.mark.api
class Base_Api_Test(object):
    '''
    Base class
    '''
    @classmethod
    def setup_class(self):
        """ setup any state specific to the execution of the given class (which
        usually contains tests).
        """
        plugin = pytest.config.pluginmanager.getplugin("plugins.pytest_restqa.pytest_restqa")
        assert plugin, 'Unable to find pytest_restqa plugin'
        self.testsetup = plugin.TestSetup

    @property
    def credentials(self):
        '''convenient access to credentials'''
        return self.testsetup.credentials

    @property
    def api(self):
        '''convenient access to api'''
        return self.testsetup.api

    @classmethod
    def teardown_class(self):
        '''
        Perform any required test teardown
        '''

    def has_credentials(self, ctype, sub_ctype=None, fields=[]):
        '''
        assert whether requested credentials are present
        '''

        # Make sure credentials.yaml has ctype we need
        assert ctype in self.testsetup.credentials, \
            "No '%s' credentials defined in credentals.yaml" % ctype
        creds = self.testsetup.credentials[ctype]

        # Ensure requested sub-type is present
        if sub_ctype:
            assert sub_ctype in creds, \
                "No '%s' '%s' credentials defined in credentals.yaml" % \
                (ctype, sub_ctype)
            creds = creds[sub_ctype]

        # Ensure requested fields are present
        if fields:
            assert all([field in creds for field in fields]), \
                "Missing required credentials (%s) for section '%s' in credentials.yaml" % \
                (', '.join(fields), ctype)

        return True

    @contextlib.contextmanager
    def current_user(self, username, password):
        '''
        Context manager to allow running tests as an alternative login user.
        '''
        try:
            previous_auth = self.api.session.auth
            self.api.login(username, password)
            yield
        finally:
            self.api.session.auth = previous_auth
