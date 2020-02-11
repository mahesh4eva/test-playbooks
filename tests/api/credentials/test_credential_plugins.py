import re

import base64
import fauxfactory
import pytest
import requests
from urllib.parse import urljoin

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from awxkit.config import config
from awxkit import utils, exceptions
from kubernetes.stream import stream

from tests.api import APITest


@pytest.fixture(scope='class')
def k8s_conjur(gke_client_cscope, request):
    K8sClient = gke_client_cscope(config.credentials)
    prefix = 'conjur'
    cluster_domain = 'services.k8s.tower-qe.testing.ansible.com'
    deployment_name = K8sClient.random_deployment_name(prefix)
    containerspec = [{'name': '{}-{}'.format(deployment_name, 'app'),
                        'image': 'cyberark/conjur',
                        'ports': [{'containerPort': 80, 'protocol': 'TCP'}],
                        'env': [{'name': 'DATABASE_URL',
                                'value': 'postgres://postgres@{}/postgres'.format(deployment_name)},
                                {'name': 'CONJUR_DATA_KEY',
                                 'value': config.credentials.conjur.datakey}],
                        'command': ['conjurctl'],
                        'args': ['server']},
                     {'name': '{}-{}'.format(deployment_name, 'pg'),
                      'image': 'postgres:9.3',
                      'ports': [{'containerPort': 5432, 'protocol': 'TCP'}]}]
    portspec = [{'name': 'conjur',
                     'port': 80,
                     'protocol': 'TCP',
                     'targetPort': 80},
                     {'name': 'postgres',
                     'port': 5432,
                     'protocol': 'TCP',
                     'targetPort': 5432}]
    conjur_deployment = K8sClient.generate_deployment(deployment_name, containerspec)
    conjur_service = K8sClient.generate_service(deployment_name, portspec)
    K8sClient.apps.create_namespaced_deployment(body=conjur_deployment, namespace='default')
    K8sClient.core.create_namespaced_service(body=conjur_service, namespace='default')
    pod_name = K8sClient.core.list_namespaced_pod('default', label_selector='run={}'.format(deployment_name)).items[0].metadata.name
    request.addfinalizer(lambda: K8sClient.destroy(deployment_name))
    utils.logged_sleep(60) # Sleeping for conjur to initialize the database. This will happen only once for the class.
    api_key = None
    conjur_url = "https://http-{}-port-80.{}".format(deployment_name, cluster_domain)
    utils.poll_until(lambda: requests.get(conjur_url).status_code == 200, timeout=120)
    try:
        deploy_info = stream(K8sClient.core.connect_get_namespaced_pod_exec,
                             pod_name,
                             'default',
                             container='{}-app'.format(deployment_name),
                             command=['conjurctl', 'account', 'create', 'test'],
                             stderr=True,
                             stdin=False,
                             stdout=True,
                             tty=False)
        api_key = re.search(r'API key for admin: ([^\s]+)', deploy_info).group(1)
    except:
        pytest.skip('Unable to get API Key')

    def create_conjur_secrets(token, secret_id, var_value_tuples=[]):
        policy_body = '\n    - !variable '.join([v[0] for v in var_value_tuples])
        policy = '- !policy\n  id: {}\n  body:\n    - !variable {}'.format(secret_id, policy_body)
        path = urljoin(conjur_url, '/'.join([
            'policies', account, 'policy', 'root'
        ]))
        resp = requests.put(
            path,
            data=policy,
            headers={'Authorization': 'Token token="{}"'.format(token)}
        )
        resp.raise_for_status()
        for v in var_value_tuples:

            # set a secret variable value
            path = urljoin(conjur_url, '/'.join([
                'secrets', account, 'variable', '{}/{}'.format(secret_id, v[0])
            ]))
            resp = requests.post(
                path,
                data=v[1],
                headers={'Authorization': 'Token token="{}"'.format(token)}
            )
            resp.raise_for_status()
    try:
        account = 'test'
        username = 'admin'
        resp = requests.post(
            urljoin(conjur_url, '/'.join(['authn', account, username, 'authenticate'])),
            headers={'Content-Type': 'text/plain'},
            data=api_key
        )
        token = base64.b64encode(resp.content).decode('utf-8')
        resp.raise_for_status()
        create_conjur_secrets(token, 'super', var_value_tuples=[('secret', 'CLASSIFIED'),
                                                          ('vault_1', 'secret1'),
                                                          ('vault_2', 'secret2'),
                                                          ])

    except:
        pytest.skip('Unable to populate conjur')
    conjur_info = {'url': conjur_url, 'api_key': api_key}
    return conjur_info


@pytest.mark.usefixtures('authtoken')
class TestConjurCredential(APITest):

    def create_conjur_credential(self, factories, v2, url, api_key, account, username):
        # create a credential w/ a conjur api_key
        cred_type = v2.credential_types.get(
            managed_by_tower=True,
            name='CyberArk Conjur Secret Lookup'
        ).results.pop()
        inputs = {
            'url': url,
            'api_key': api_key,
            'account': account,
            'username': username,
        }
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type,
            inputs=inputs
        )
        return v2.credentials.post(payload)

    def create_conjur_machine_credential(self, factories, v2, conjur_credential):
        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        # associate cred.username -> conjur_cred
        metadata = {
            'secret_path': 'super/secret',
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=conjur_credential.id,
            metadata=metadata
        ))
        return credential

    def launch_job(self, factories, v2, path, secret_version=None,
                   url=None, api_key=None, account=None, username=None):

        conjur_credential = self.create_conjur_credential(factories, v2, url=url, api_key=api_key, account=account, username=username)

        # create an SSH credential
        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        # associate cred.username -> conjur_cred
        metadata = {
            'secret_path': path,
        }
        if secret_version:
            metadata['secret_version'] = secret_version
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=conjur_credential.id,
            metadata=metadata
        ))

        # assign the SSH credential to a JT and run it
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='ping.yml',
                                       credential=credential)
        return jt.launch().wait_until_completed()

    @pytest.mark.parametrize('path, secret_version, expected', [
        ['super/secret', None, 'CLASSIFIED'],
        ['super/secret', '1', 'CLASSIFIED'],
    ])
    def test_conjur_secret_lookup(self, factories, v2, path, secret_version, expected, k8s_conjur):
        job = self.launch_job(factories, v2, path, secret_version, username='admin',
                              account='test', url=k8s_conjur['url'], api_key=k8s_conjur['api_key'])
        job.assert_successful()
        assert '-u {}'.format(expected) in ' '.join(job.job_args)

    def test_conjur_secret_bad_path(self, factories, v2, k8s_conjur):
        job = self.launch_job(factories, v2, 'super/missing', username='admin',
                              account='test', url=k8s_conjur['url'], api_key=k8s_conjur['api_key'])
        assert not job.is_successful
        assert 'requests.exceptions.HTTPError: 404 Client Error' in job.result_traceback

    def test_conjur_secret_bad_url(self, factories, v2, k8s_conjur):
        job = self.launch_job(factories, v2, '', url='http://missing.local:8200', api_key=k8s_conjur['api_key'])
        assert not job.is_successful
        assert 'Failed to establish a new connection: [Errno -2] Name or service not known' in job.result_traceback

    @pytest.mark.parametrize('api_key_permutations', [
        {'api_key': False, 'account': 'test', 'username': 'admin'},
        {'account': 'missing-account', 'username': 'admin', 'api_key': True},
        {'username': 'whodis', 'account': 'test', 'api_key': True}],
        ids=['wrong_key', 'wrong_account', 'wrong_user']
    )
    def test_conjur_secret_bad_api_key(self, factories, v2, k8s_conjur, api_key_permutations):
        if api_key_permutations['api_key']:
            api_key = k8s_conjur['api_key']
        else:
            api_key = "WRONG"
        job = self.launch_job(factories, v2, '', url=k8s_conjur['url'], api_key=api_key,
                              account=api_key_permutations['account'], username=api_key_permutations['username'])
        assert not job.is_successful
        assert 'requests.exceptions.HTTPError: 401 Client Error: Unauthorized' in job.result_traceback

    def test_conjur_secret_can_decrypt_ansible_vault(self, factories, v2, k8s_conjur):
        secrets = [('first', 'super/vault_1'), ('second', 'super/vault_2')]
        conjur_credential = self.create_conjur_credential(factories, v2, url=k8s_conjur['url'], api_key=k8s_conjur['api_key'], account='test', username='admin')
        jt = factories.job_template(playbook='multivault.yml')
        for s in secrets:
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='vault').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type,
                inputs={'vault_id': s[0]}
            )
            credential = v2.credentials.post(payload)
            metadata = {
                'secret_path': s[1],
            }
            credential.related.input_sources.post(dict(
                input_field_name='vault_password',
                source_credential=conjur_credential.id,
                metadata=metadata
            ))
            jt.add_credential(credential)
        job = jt.launch().wait_until_completed()
        assert job.is_successful

    def test_conjur_custom_credential(self, factories, v2, k8s_conjur):
        conjur_credential = self.create_conjur_credential(factories, v2, url=k8s_conjur['url'], api_key=k8s_conjur['api_key'], account='test', username='admin')
        inputs = dict(fields=[dict(id='field_one', label='FieldOne', secret=True)])
        injectors = dict(extra_vars=dict(extra_var_from_field_one='{{ field_one }}'))
        credential_type = factories.credential_type(inputs=inputs, injectors=injectors)

        credential = factories.credential(credential_type=credential_type)
        metadata = {
            'secret_path': 'super/secret',
        }
        credential.related.input_sources.post(dict(
            input_field_name='field_one',
            source_credential=conjur_credential.id,
            metadata=metadata
            ))
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='debug_hostvars.yml')
        jt.add_extra_credential(credential)
        job = jt.launch().wait_until_completed()
        job.assert_successful()

        hostvars = job.related.job_events.get(host=host.id, task='debug', event__startswith='runner_on_ok').results.pop().event_data.res.hostvars
        assert hostvars[host.name]['extra_var_from_field_one'] == 'CLASSIFIED'

    def test_conjur_credentials_can_be_used_in_prompt(self, factories, v2, k8s_conjur, job_template_prompt_for_credential):
        conjur_credential = self.create_conjur_credential(factories, v2, url=k8s_conjur['url'], api_key=k8s_conjur['api_key'], account='test', username='admin')

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'secret_path': 'super/secret',
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=conjur_credential.id,
            metadata=metadata,
        ))

        with pytest.raises(exceptions.NoContent):
            job_template_prompt_for_credential.related.credentials.post(dict(id=credential.id))
        job = job_template_prompt_for_credential.launch().wait_until_completed()
        job.assert_successful()

    def test_conjur_RBAC_users_can_be_assigned_use_on_credentials(self, factories, v2, k8s_conjur):
        conjur_credential = self.create_conjur_credential(factories, v2, url=k8s_conjur['url'], api_key=k8s_conjur['api_key'], account='test', username='admin')
        org = factories.organization()
        user = factories.user(organization=org)

        credential = self.create_conjur_machine_credential(factories, v2, conjur_credential)
        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'use')

        jt = factories.job_template()
        resources = ['inventory', 'credential', 'project']
        for r in resources:
            jt.ds[r].patch(organization=org.id)
            jt.ds[r].set_object_roles(user, 'use')
        jt.set_object_roles(user, 'admin')
        utils.logged_sleep(5)

        with self.current_user(username=user.username, password=user.password):
            jt.patch(credential=credential.id)
            job = jt.launch().wait_until_completed()
        assert job.is_successful

    def test_conjur_RBAC_users_cannot_change_linkage_without_lookup_cred_use(self, factories, v2, k8s_conjur):
        conjur_credential = self.create_conjur_credential(factories, v2, url=k8s_conjur['url'], api_key=k8s_conjur['api_key'], account='test', username='admin')
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'admin')
        conjur_credential.patch(org=org.id)

        metadata = {
            'secret_path': 'super/secret'
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=conjur_credential.id,
            metadata=metadata,
        ))
        cred_source = credential.related.input_sources.get().results.pop()
        dangerous_metadata = {
            'secret_path': 'super/launch-codes'
        }
        with self.current_user(username=user.username, password=user.password):
            with pytest.raises(exceptions.Forbidden):
                cred_source.patch(metadata=dangerous_metadata)
        assert credential.related.input_sources.get().results.pop().metadata == metadata

    def test_conjur_delete_retrieval_cred(self, factories, v2, k8s_conjur):
        conjur_credential = self.create_conjur_credential(factories, v2, url=k8s_conjur['url'], api_key=k8s_conjur['api_key'], account='test', username='admin')
        dependent_creds = []
        for _ in range(5):
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type
            )
            credential = v2.credentials.post(payload)

            metadata = {
                'secret_path': 'super/secret'
            }
            credential.related.input_sources.post(dict(
                input_field_name='username',
                source_credential=conjur_credential.id,
                metadata=metadata,
            ))
            dependent_creds.append(credential)
        conjur_credential.delete()
        for c in dependent_creds:
            linkage = c.related.input_sources.get().results
            assert len(linkage) == 0


@pytest.mark.usefixtures('authtoken')
class TestHashiCorpVaultCredentials(APITest):

    def create_hashicorp_vault_credential(self, factories, v2, url, token, hashicorp_api_version):
        cred_type = v2.credential_types.get(
            managed_by_tower=True,
            name='HashiCorp Vault Secret Lookup'
        ).results.pop()
        inputs = {
            'url': url,
            'token': token,
            'api_version': hashicorp_api_version
        }
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type,
            inputs=inputs
        )
        return v2.credentials.post(payload)

    def launch_job(self, factories, v2, hashicorp_api_version, secret_version, path, url=None,
                    token=config.credentials.hashivault.token, secret_key='username'):

        hashi_credential = self.create_hashicorp_vault_credential(factories, v2, url, token, hashicorp_api_version)

        # create an SSH credential
        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        # associate cred.username -> hashi_cred
        metadata = {
            'secret_path': path,
            'secret_key': secret_key,
        }
        if secret_version:
            metadata['secret_version'] = secret_version
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=hashi_credential.id,
            metadata=metadata
        ))

        # assign the SSH credential to a JT and run it
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='ping.yml',
                                       credential=credential)
        return jt.launch().wait_until_completed()

    @pytest.mark.parametrize('hashicorp_api_version, secret_version, path, expected', [
        ['v1', None, '/kv/example-user/', 'unversioned-username'],
        ['v2', None, '/versioned/example-user', 'latest-username'],
        ['v2', '1', '/versioned/example-user', 'old-username'],
        ['v2', None, '/versioned/subfolder/example-user', 'sub-username'],
    ])
    def test_hashicorp_vault_kv_lookup(self, factories, v2, hashicorp_api_version,
                                       secret_version, path, expected, k8s_vault):
        """
        Verify that a v1 KV secret can be pulled from a Hashicorp Vault API
        and injected into an ansible-playbook run.

        This test assumes that you have a HashiCorp Vault API with a v1 K/V
        engine and a path of /kv/example-user/ that provides a value for the
        "username" key lookup

        This test also assumes that you have a HashiCorp Vault API with a v2
        (versioned) K/V engine and a path of /versioned/example-user/ that
        provides a versioned value for the "username" key lookup (with at least
        two versions)
        """
        job = self.launch_job(factories, v2, hashicorp_api_version, secret_version, path, url=k8s_vault)
        job.assert_successful()
        assert '-u {}'.format(expected) in ' '.join(job.job_args)

    @pytest.mark.parametrize('hashicorp_api_version', ['v1', 'v2'])
    @pytest.mark.parametrize('path', [
        '/missing/path',
        '/missing/',
        'a',
    ])
    def test_hashicorp_vault_kv_bad_path(self, factories, v2, hashicorp_api_version, path, k8s_vault):
        job = self.launch_job(factories, v2, hashicorp_api_version, None, path, url=k8s_vault)
        assert not job.is_successful
        assert 'requests.exceptions.HTTPError: 404 Client Error' in job.result_traceback

    @pytest.mark.parametrize('hashicorp_api_version, secret_version, path', [
        ['v1', None, '/kv/example-user/'],
        ['v2', None, '/versioned/example-user'],
        ['v2', '1', '/versioned/example-user'],
    ])
    def test_hashicorp_vault_kv_bad_key(self, factories, v2, hashicorp_api_version,
                                        secret_version, path, k8s_vault):
        job = self.launch_job(factories, v2, hashicorp_api_version, secret_version, path, url=k8s_vault,
                          secret_key='key-does-not-exist')
        assert not job.is_successful
        assert '{} is not present at {}'.format(
            'key-does-not-exist',
            path
        ) in job.result_traceback

    @pytest.mark.parametrize('hashicorp_api_version', ['v1', 'v2'])
    def test_hashicorp_vault_kv_bad_url(self, factories, v2, hashicorp_api_version):
        job = self.launch_job(factories, v2, hashicorp_api_version, None, '/any/path', url='http://missing.local:8200')
        assert not job.is_successful
        assert 'Failed to establish a new connection: [Errno -2] Name or service not known' in job.result_traceback

    @pytest.mark.parametrize('hashicorp_api_version', ['v1', 'v2'])
    def test_hashicorp_vault_kv_bad_token(self, factories, v2, hashicorp_api_version, k8s_vault):
        job = self.launch_job(factories, v2, hashicorp_api_version, None, '/any/path', url=k8s_vault,
                          token='totally-incorrect-token')
        assert not job.is_successful
        assert '403 Client Error: Forbidden' in job.result_traceback

    def test_hashicorp_vault_secret_can_decrypt_ansible_vault(self, factories, v2, k8s_vault):
        secrets = [('first', '/kv/vault_1'), ('second', '/kv/vault_2')]
        vault_credential = self.create_hashicorp_vault_credential(factories, v2, k8s_vault, config.credentials.hashivault.token, 'v1')
        jt = factories.job_template(playbook='multivault.yml')
        for s in secrets:
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='vault').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type,
                inputs={'vault_id': s[0]}
            )
            credential = v2.credentials.post(payload)
            metadata = {
                'secret_path': s[1],
                'secret_key': 'password'
            }
            credential.related.input_sources.post(dict(
                input_field_name='vault_password',
                source_credential=vault_credential.id,
                metadata=metadata
            ))
            jt.add_credential(credential)
        job = jt.launch().wait_until_completed()
        assert job.is_successful

    def test_hashicorp_vault_custom_credential(self, factories, v2, k8s_vault):
        vault_credential = self.create_hashicorp_vault_credential(factories, v2, k8s_vault, config.credentials.hashivault.token, 'v1')
        inputs = dict(fields=[dict(id='field_one', label='FieldOne', secret=True)])
        injectors = dict(extra_vars=dict(extra_var_from_field_one='{{ field_one }}'))
        credential_type = factories.credential_type(inputs=inputs, injectors=injectors)

        credential = factories.credential(credential_type=credential_type)
        metadata = {
            'secret_path': '/kv/example-user/',
            'secret_key': 'username'
        }
        credential.related.input_sources.post(dict(
            input_field_name='field_one',
            source_credential=vault_credential.id,
            metadata=metadata
            ))
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='debug_hostvars.yml')
        jt.add_extra_credential(credential)
        job = jt.launch().wait_until_completed()
        job.assert_successful()

        hostvars = job.related.job_events.get(host=host.id, task='debug', event__startswith='runner_on_ok').results.pop().event_data.res.hostvars
        assert hostvars[host.name]['extra_var_from_field_one'] == 'unversioned-username'

    def test_hashicorp_vault_credentials_can_be_used_in_prompt(self, factories, v2, k8s_vault, job_template_prompt_for_credential):
        vault_credential = self.create_hashicorp_vault_credential(factories, v2, k8s_vault, config.credentials.hashivault.token, 'v1')

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'secret_path': '/kv/example-user/',
            'secret_key': 'username'
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=vault_credential.id,
            metadata=metadata,
        ))

        with pytest.raises(exceptions.NoContent):
            job_template_prompt_for_credential.related.credentials.post(dict(id=credential.id))
        job = job_template_prompt_for_credential.launch().wait_until_completed()
        job.assert_successful()

    def test_hashicorp_vault_RBAC_users_can_be_assigned_use_on_credentials(self, factories, v2, k8s_vault):
        hashi_credential = self.create_hashicorp_vault_credential(factories, v2, k8s_vault, config.credentials.hashivault.token, 'v1')
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'secret_path': '/kv/example-user/',
            'secret_key': 'username',
        }

        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=hashi_credential.id,
            metadata=metadata
        ))
        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'use')

        jt = factories.job_template()
        resources = ['inventory', 'credential', 'project']
        for r in resources:
            jt.ds[r].patch(organization=org.id)
            jt.ds[r].set_object_roles(user, 'use')
        jt.set_object_roles(user, 'admin')

        with self.current_user(username=user.username, password=user.password):
            jt.patch(credential=credential.id)
            job = jt.launch().wait_until_completed()

        assert job.is_successful

    def test_hashicorp_vault_RBAC_users_cannot_change_linkage_without_lookup_cred_use(self, factories, v2, k8s_vault):
        hashi_credential = self.create_hashicorp_vault_credential(factories, v2, k8s_vault, config.credentials.hashivault.token, 'v1')
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'admin')
        hashi_credential.patch(org=org.id)

        metadata = {
            'secret_path': '/kv/example-user/',
            'secret_key': 'username',
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=hashi_credential.id,
            metadata=metadata,
        ))
        cred_source = credential.related.input_sources.get().results.pop()
        dangerous_metadata = {
            'secret_path': 'super/dangerous',
            'secret_key': 'launch_codes'
        }
        with self.current_user(username=user.username, password=user.password):
            with pytest.raises(exceptions.Forbidden):
                cred_source.patch(metadata=dangerous_metadata)
        assert credential.related.input_sources.get().results.pop().metadata == metadata

    def test_hashicorp_vault_delete_retrieval_cred(self, factories, v2, k8s_vault):
        hashi_credential = self.create_hashicorp_vault_credential(factories, v2, k8s_vault, config.credentials.hashivault.token, 'v1')
        dependent_creds = []
        for _ in range(5):
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type
            )
            credential = v2.credentials.post(payload)

            metadata = {
                'secret_path': '/kv/example-user/',
                'secret_key': 'username',
            }
            credential.related.input_sources.post(dict(
                input_field_name='username',
                source_credential=hashi_credential.id,
                metadata=metadata,
            ))
            dependent_creds.append(credential)
        hashi_credential.delete()
        for c in dependent_creds:
            linkage = c.related.input_sources.get().results
            assert len(linkage) == 0


@pytest.mark.usefixtures('authtoken')
class TestHashiCorpSSHEngine(APITest):

    def launch_job(self, factories, v2, path, role, passphrase,
                   valid_principals=None, url=None, token=None):

        token = token or config.credentials.hashivault.token
        # create a credential w/ a hashicorp token
        cred_type = v2.credential_types.get(
            managed_by_tower=True,
            name='HashiCorp Vault Signed SSH'
        ).results.pop()
        inputs = {
            'url': url,
            'token': token,
        }
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type,
            inputs=inputs
        )
        hashi_credential = v2.credentials.post(payload)

        # create an keypair so the private half can be signed
        key = rsa.generate_private_key(
            public_exponent=65537, key_size=4096, backend=default_backend()
        )
        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        if passphrase is None:
            encryption = serialization.NoEncryption()
        else:
            encryption = serialization.BestAvailableEncryption(passphrase.encode('utf-8'))
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type,
            inputs={
                'ssh_key_data': key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=encryption
                ).decode('utf-8'),
                'ssh_key_unlock': passphrase or '',
            }
        )
        credential = v2.credentials.post(payload)

        # associate cred.username -> hashi_cred
        metadata = {
            'public_key': key.public_key().public_bytes(
                encoding=serialization.Encoding.OpenSSH,
                format=serialization.PublicFormat.OpenSSH
            ).decode('utf-8'),
            'secret_path': path,
            'role': role,
        }
        if valid_principals:
            metadata['valid_principals'] = valid_principals
        credential.related.input_sources.post(dict(
            input_field_name='ssh_public_key_data',
            source_credential=hashi_credential.id,
            metadata=metadata,
        ))

        # assign the SSH credential to a JT and run it
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='ping.yml',
                                       credential=credential)
        return jt.launch().wait_until_completed()

    @pytest.mark.parametrize('passphrase', [None, 'some-pass'])
    def test_hashicorp_ssh_signer(self, factories, v2, passphrase, k8s_vault):
        """
        Test support for https://www.vaultproject.io/docs/secrets/ssh/signed-ssh-certificates.html
        """
        job = self.launch_job(factories, v2, 'my-signer', 'my-role', passphrase, url=k8s_vault)
        job.assert_successful()
        assert re.search('Identity added', job.result_stdout) is not None, job.result_stdout

    def test_hashicorp_ssh_signer_bad_path(self, factories, v2, k8s_vault):
        job = self.launch_job(factories, v2, 'missing-backend', 'foo', None, url=k8s_vault)
        assert job.is_successful is False
        assert 'requests.exceptions.HTTPError: 404 Client Error' in job.result_traceback

    def test_hashicorp_ssh_signer_restricted_user(self, factories, v2, k8s_vault):
        job = self.launch_job(factories, v2, 'my-signer', 'my-role', None,
                          valid_principals='root', url=k8s_vault)
        assert job.is_successful is False
        assert 'requests.exceptions.HTTPError: 400 Client Error' in job.result_traceback


@pytest.mark.usefixtures('authtoken')
class TestAzureKVCredentials(APITest):

    def create_azurekv_credential(self, factories, v2, url):
        cred_type = v2.credential_types.get(
        managed_by_tower=True,
        name='Microsoft Azure Key Vault'
        ).results.pop()
        inputs = {
            'url': url,
            'client': config.credentials.cloud.azure.client_id,
            'secret': config.credentials.cloud.azure.secret,
            'tenant': config.credentials.cloud.azure.tenant,
        }
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type,
            inputs=inputs
        )
        return v2.credentials.post(payload)

    def launch_job(self, factories, v2, url, secret_field, version=None):
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')

        # create an SSH credential
        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        # associate cred.username -> azure_credential
        metadata = {
            'secret_field': secret_field,
        }
        if version:
            metadata['secret_version'] = version
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=azure_credential.id,
            metadata=metadata,
        ))

        # assign the SSH credential to a JT and run it
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='ping.yml',
                                       credential=credential)
        return jt.launch().wait_until_completed()

    @pytest.mark.parametrize('url, key, expected, version', [
        ['https://qecredplugin.vault.azure.net/', 'example-user', 'latest-username', None],
        ['https://qecredplugin.vault.azure.net/', 'example-user', 'from-azure',
         '74d97f8e2ce1470ba3bbd0f7407a75b4'],
    ])
    def test_azure_key_vault_lookup(self, factories, v2, url, key, expected, version):
        """
        Verify that a secret can be looked up from Azure Key Vault.

        This test assumes that you have an Azure Key Vault with a secret
        named `example-user` and a value of `from-azure`.
        """
        job = self.launch_job(factories, v2, url, key, version=version)
        job.assert_successful()
        assert '-u {}'.format(expected) in ' '.join(job.job_args)

    def test_azure_key_vault_bad_key(self, factories, v2):
        job = self.launch_job(factories, v2, 'https://qecredplugin.vault.azure.net/', 'missing-key')
        assert job.is_successful is False
        assert 'Secret not found: missing-key' in job.result_traceback

    def test_azure_key_vault_bad_version(self, factories, v2):
        job = self.launch_job(factories, v2,
                          'https://qecredplugin.vault.azure.net/', 'example-user',
                          'incorrect-version')
        assert job.is_successful is False
        assert 'KeyVaultErrorException' in job.result_traceback

    def test_azure_key_vault_cred_can_decrypt_ansible_vault(self, factories, v2):
        jt = factories.job_template(playbook='multivault.yml')
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')
        for s in [('first', 'vault1'), ('second', 'vault2')]:
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='vault').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type,
                inputs={'vault_id': s[0]}
            )
            credential = v2.credentials.post(payload)

            # associate cred.username -> azure_credential
            metadata = {
                'secret_field': s[1],
            }
            credential.related.input_sources.post(dict(
                input_field_name='vault_password',
                source_credential=azure_credential.id,
                metadata=metadata,
            ))
            jt.add_credential(credential)
        job = jt.launch().wait_until_completed()
        assert job.is_successful

    def test_azure_key_vault_custom_credential(self, factories, v2):
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')
        inputs = dict(fields=[dict(id='field_one', label='FieldOne', secret=True)])
        injectors = dict(extra_vars=dict(extra_var_from_field_one='{{ field_one }}'))
        credential_type = factories.credential_type(inputs=inputs, injectors=injectors)

        credential = factories.credential(credential_type=credential_type)
        metadata = {
            'secret_field': 'example-user'
        }
        credential.related.input_sources.post(dict(
            input_field_name='field_one',
            source_credential=azure_credential.id,
            metadata=metadata
            ))
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='debug_hostvars.yml')
        jt.add_extra_credential(credential)
        job = jt.launch().wait_until_completed()
        job.assert_successful()

        hostvars = job.related.job_events.get(host=host.id, task='debug', event__startswith='runner_on_ok').results.pop().event_data.res.hostvars
        assert hostvars[host.name]['extra_var_from_field_one'] == 'latest-username'

    def test_azure_key_vault_RBAC_users_can_be_assigned_use_on_credentials(self, factories, v2):
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'secret_field': 'example-user'
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=azure_credential.id,
            metadata=metadata,
        ))

        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'use')

        jt = factories.job_template()
        resources = ['inventory', 'credential', 'project']
        for r in resources:
            jt.ds[r].patch(organization=org.id)
            jt.ds[r].set_object_roles(user, 'use')
        jt.set_object_roles(user, 'admin')

        with self.current_user(username=user.username, password=user.password):
            jt.patch(credential=credential.id)
            job = jt.launch().wait_until_completed()

        assert job.is_successful

    def test_azure_key_vault_RBAC_users_cannot_change_linkage_without_lookup_cred_use(self, factories, v2):
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'admin')
        azure_credential.patch(org=org.id)

        metadata = {
            'secret_field': 'example-user'
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=azure_credential.id,
            metadata=metadata,
        ))
        cred_source = credential.related.input_sources.get().results.pop()
        dangerous_metadata = {
            'secret_field': 'launch-codes'
        }
        with self.current_user(username=user.username, password=user.password):
            with pytest.raises(exceptions.Forbidden):
                cred_source.patch(metadata=dangerous_metadata)
        assert credential.related.input_sources.get().results.pop().metadata == metadata

    def test_azure_key_vault_credentials_can_be_used_in_prompt(self, factories, v2, job_template_prompt_for_credential):
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'secret_field': 'example-user'
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=azure_credential.id,
            metadata=metadata,
        ))

        with pytest.raises(exceptions.NoContent):
            job_template_prompt_for_credential.related.credentials.post(dict(id=credential.id))

        job = job_template_prompt_for_credential.launch().wait_until_completed()

        job.assert_successful()

    def test_azure_key_vault_delete_retrieval_cred(self, factories, v2):
        azure_credential = self.create_azurekv_credential(factories, v2, 'https://qecredplugin.vault.azure.net/')
        dependent_creds = []
        for _ in range(5):
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type
            )
            credential = v2.credentials.post(payload)

            metadata = {
                'secret_field': 'example-user'
            }
            credential.related.input_sources.post(dict(
                input_field_name='username',
                source_credential=azure_credential.id,
                metadata=metadata,
            ))
            dependent_creds.append(credential)
        azure_credential.delete()
        for c in dependent_creds:
            linkage = c.related.input_sources.get().results
            assert len(linkage) == 0


@pytest.fixture
def check_cyberark_aim(request):
    """
    Check if cyberark_aim credentials are available on the config and that the
    server is reachable from the system under test. Unless the credentials and
    server are available, the suite is skipped.
    """
    aim_config = getattr(config.credentials, 'cyberark_aim', None)
    aim_url = getattr(aim_config, 'url', None)

    if not aim_url:
        pytest.skip('no cyberark aim credentials configured')

    factories = request.getfixturevalue('factories')
    v2 = request.getfixturevalue('v2')

    host = factories.host()
    cred = factories.credential()
    job = v2.ad_hoc_commands.post({
        'inventory': host.inventory,
        'credential': cred.id,
        'module_name': 'shell',
        'module_args': 'curl -k -i -s {0}'.format(aim_url)
    })

    job.wait_until_completed()
    if job.status != 'successful':
        pytest.skip('unable to check if cyberark aim server is available')

    job_events = job.related.events.get()
    if '200 OK' not in ''.join([e.stdout for e in job_events.results]):
        pytest.skip('cyberark aim server is unavailable')


@pytest.mark.github('https://github.com/ansible/tower-qa/issues/4607', skip=True)
@pytest.mark.usefixtures(
    'authtoken', 'check_cyberark_aim')
class TestCyberArkAimCredentials(APITest):

    def create_aim_credential(self, factories, v2, url=None,
                              app_id=None, client_cert=None, client_key=None, verify=False):
        aim_creds = config.credentials.cyberark_aim

        url = url or aim_creds.url
        client_cert = client_cert or aim_creds.client_cert
        client_key = client_key or aim_creds.client_key
        app_id = app_id or aim_creds.app_id
        # create a credential w/ cyberark aim creds
        cred_type = v2.credential_types.get(
            managed_by_tower=True,
            name='CyberArk AIM Central Credential Provider Lookup'
        ).results.pop()
        inputs = {
            'url': url,
            'app_id': app_id,
            'client_key': client_key,
            'client_cert': client_cert,
            'verify': verify
        }
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type,
            inputs=inputs
        )
        return v2.credentials.post(payload)

    def launch_job(self, factories, v2, object_query=None, object_query_format=None,
                   url=None, app_id=None, client_cert=None, client_key=None,
                   reason=None, verify=False):
        aim_creds = config.credentials.cyberark_aim
        url = url or aim_creds.url
        client_cert = client_cert or aim_creds.client_cert
        client_key = client_key or aim_creds.client_key
        app_id = app_id or aim_creds.app_id
        object_query = object_query or aim_creds.object_query
        object_query_format = object_query_format or aim_creds.object_query_format
        aim_credential = self.create_aim_credential(factories, v2, url=url, app_id=app_id, client_cert=client_cert,
                                                    client_key=client_key, verify=False)
        # create an SSH credential
        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        # associate cred.username -> aim_cred
        metadata = {
            'object_query': object_query,
            'object_query_format': object_query_format,
        }
        if reason:
            metadata['reason'] = reason
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=aim_credential.id,
            metadata=metadata
        ))

        # assign the SSH credential to a JT and run it
        host = factories.host()
        jt = factories.job_template(
            inventory=host.ds.inventory,
            playbook='ping.yml',
            credential=credential
        )
        return jt.launch().wait_until_completed()

    def test_cyberark_aim_lookup(self, factories, v2):
        """
        Verify that an object secret can be pulled from a cyberark aim API
        and injected into an ansible-playbook run.

        Setup of secret values (and authentication) on a cyberark aim server
        involves restarting services on a Windows Server vm. We haven't
        automated this yet, so for now we use a hard-coded object query and
        expected value included with the server credentials.
        """
        expected_value = 'foobar123'
        job = self.launch_job(factories, v2, verify=False)
        job.assert_successful()
        assert any([expected_value in args for args in job.job_args])

    def test_cyberark_aim_secret_bad_query(self, factories, v2):
        bad_query = 'Safe=TestSafe;Object=WrongObject'
        job = self.launch_job(factories, v2, verify=False, object_query=bad_query)
        assert not job.is_successful
        assert 'requests.exceptions.HTTPError: 404 Client Error' in job.result_traceback
        assert 'Not Found for url' in job.result_traceback

    def test_cyberark_aim_secret_bad_url(self, factories, v2):
        bad_url = 'http://missing.local:8200'
        job = self.launch_job(factories, v2, verify=False, url=bad_url)
        assert not job.is_successful
        assert 'Failed to establish a new connection: [Errno -2] Name or service not known' in job.result_traceback

    def test_cyberark_aim_secret_bad_client_cert(self, factories, v2):
        bad_cert = '-----BEGIN CERTIFICATE-----AAAA-----END CERTIFICATE-----'
        job = self.launch_job(factories, v2, verify=False, client_cert=bad_cert)
        assert not job.is_successful
        assert 'OpenSSL.SSL.Error' in job.result_traceback

    def test_cyberark_aim_secret_bad_client_key(self, factories, v2):
        bad_key = '-----BEGIN PRIVATE KEY-----BBBB-----END PRIVATE KEY-----'
        job = self.launch_job(factories, v2, verify=False, client_key=bad_key)
        assert not job.is_successful
        assert 'OpenSSL.SSL.Error' in job.result_traceback

    def test_cyberark_aim_secret_can_decrypt_ansible_vault(self, factories, v2):
        jt = factories.job_template(playbook='multivault.yml')
        aim_creds = config.credentials.cyberark_aim
        aim_credential = self.create_aim_credential(factories, v2, url=aim_creds.url,
                                                    app_id=aim_creds.app_id, client_cert=aim_creds.client_cert,
                                                    client_key=aim_creds.client_key, verify=False)
        for s in [('first', 'vault_1'), ('second', 'vault_2')]:
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='vault').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type,
                inputs={'vault_id': s[0]}
            )
            credential = v2.credentials.post(payload)
            object_query = 'Safe=TestSafe;Object={}'.format(s[1])
            metadata = {
                'object_query': object_query,
                'object_query_format': aim_creds.object_query_format,
            }
            credential.related.input_sources.post(dict(
                input_field_name='vault_password',
                source_credential=aim_credential.id,
                metadata=metadata,
            ))
            jt.add_credential(credential)
        job = jt.launch().wait_until_completed()
        assert job.is_successful

    def test_cyberark_aim_credentials_can_be_used_in_prompt(self, factories, v2, job_template_prompt_for_credential):
        aim_creds = config.credentials.cyberark_aim
        aim_credential = self.create_aim_credential(factories, v2, verify=False)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'object_query': aim_creds.object_query,
            'object_query_format': aim_creds.object_query_format
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=aim_credential.id,
            metadata=metadata,
        ))

        with pytest.raises(exceptions.NoContent):
            job_template_prompt_for_credential.related.credentials.post(dict(id=credential.id))
        job = job_template_prompt_for_credential.launch().wait_until_completed()
        job.assert_successful()

    def test_cyberark_aim_RBAC_users_can_be_assigned_use_on_credentials(self, factories, v2):
        aim_creds = config.credentials.cyberark_aim
        aim_credential = self.create_aim_credential(factories, v2, url=aim_creds.url,
                                                    app_id=aim_creds.app_id, client_cert=aim_creds.client_cert,
                                                    client_key=aim_creds.client_key, verify=False)
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        metadata = {
            'object_query': aim_creds.object_query,
            'object_query_format': aim_creds.object_query_format
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=aim_credential.id,
            metadata=metadata
        ))
        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'use')

        jt = factories.job_template()
        resources = ['inventory', 'credential', 'project']
        for r in resources:
            jt.ds[r].patch(organization=org.id)
            jt.ds[r].set_object_roles(user, 'use')
        jt.set_object_roles(user, 'admin')

        with self.current_user(username=user.username, password=user.password):
            jt.patch(credential=credential.id)
            job = jt.launch().wait_until_completed()

        assert job.is_successful

    def test_cyberark_aim_RBAC_users_cannot_change_linkage_without_lookup_cred_use(self, factories, v2):
        aim_creds = config.credentials.cyberark_aim
        aim_credential = self.create_aim_credential(factories, v2)
        org = factories.organization()
        user = factories.user(organization=org)

        cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
        payload = factories.credential.payload(
            name=fauxfactory.gen_utf8(),
            description=fauxfactory.gen_utf8(),
            credential_type=cred_type
        )
        credential = v2.credentials.post(payload)

        credential.patch(organization=org.id)
        credential.set_object_roles(user, 'admin')
        aim_credential.patch(org=org.id)

        metadata = {
            'object_query': aim_creds.object_query,
            'object_query_format': aim_creds.object_query_format
        }
        credential.related.input_sources.post(dict(
            input_field_name='username',
            source_credential=aim_credential.id,
            metadata=metadata,
        ))
        cred_source = credential.related.input_sources.get().results.pop()
        dangerous_metadata = {
            'object_query': 'safe=Super;Object=Dangerous',
            'object_query_format': 'Exact'
        }
        with self.current_user(username=user.username, password=user.password):
            with pytest.raises(exceptions.Forbidden):
                cred_source.patch(metadata=dangerous_metadata)
        assert credential.related.input_sources.get().results.pop().metadata == metadata

    def test_cyberark_aim_delete_retrieval_cred(self, factories, v2):
        aim_creds = config.credentials.cyberark_aim
        aim_credential = self.create_aim_credential(factories, v2)
        dependent_creds = []
        for _ in range(5):
            cred_type = v2.credential_types.get(managed_by_tower=True, kind='ssh').results.pop()
            payload = factories.credential.payload(
                name=fauxfactory.gen_utf8(),
                description=fauxfactory.gen_utf8(),
                credential_type=cred_type
            )
            credential = v2.credentials.post(payload)

            metadata = {
                'object_query': aim_creds.object_query,
                'object_query_format': aim_creds.object_query_format
            }
            credential.related.input_sources.post(dict(
                input_field_name='username',
                source_credential=aim_credential.id,
                metadata=metadata,
            ))
            dependent_creds.append(credential)
        aim_credential.delete()
        for c in dependent_creds:
            linkage = c.related.input_sources.get().results
            assert len(linkage) == 0
