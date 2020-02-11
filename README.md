## Dependencies

You will need:

* `docker`
* `gcloud`
  * (quickstart for linux)[https://cloud.google.com/sdk/docs/quickstart-linux]
* python 3.6 (for devel and future versions)

## Tower Integration Tests

In order to run integration tests you'll need a working Tower or AWX install to
run tests against. The following steps describe building and configuring the
Tower dev containers and running tests against them.

> Note: tower-qa currently works with Python 3.6. Release branches <
> release_3.5.x use Python 2.7, if you are checking out those branches, ensure
> you use the right Python version.

To run tests you'll need an appropriate config file and inventory, tower-qa ships with several useful examples.

```
git clone git@github.com:ansible/tower.git
git clone git@github.com:ansible/tower-qa.git
cd tower
# Note: if you want anything other than devel you'll need to checkout the right tower branch and set the compose tag in order to get the right local_settings.py
cp awx/settings/local_settings.py.docker_compose awx/settings/local_settings.py

gcloud auth login
gcloud config set project ansible-tower-engineering
export COMPOSE_TAG=devel
export GCLOUD_AUTH=`gcloud auth print-access-token`
export IMAGE_REPOSITORY_AUTH=$GCLOUD_AUTH
gcloud auth configure-docker
docker pull gcr.io/ansible-tower-engineering/awx_devel:devel
make docker-compose
make ui-devel
```

Alternatively, you can achieve everything in the second block all at once:
```
cp awx/settings/local_settings.py.docker_compose awx/settings/local_settings.py && gcloud config set project ansible-tower-engineering && make ui-devel && IMAGE_REPOSITORY_AUTH=`gcloud auth print-access-token` make docker-compose COMPOSE_TAG=release_3.3.1
```

### Set up Tower-License module

```
# First create a superuser by running the following command
docker exec -it tools_awx_1 bash -c "awx-manage createsuperuser --noinput --username admin --email admin@example.com; awx-manage update_password --username admin --password XXXX; awx-manage create_preload_data"

# Or access the dev container
docker exec -it tools_awx_1 bash

# And run these commands
awx-manage createsuperuser --noinput --username admin --email admin@example.com
awx-manage update_password --username admin --password XXXX
awx-manage create_preload_data
exit

# Back to your machine terminal, clone license repo (need local ssh keys)
cd tower                      # or 'awx' -- the root directory of your cloned repo
git clone git@github.com:ansible/tower-license.git

# Then install the tower-license module in the awx venv
# It is necessary to provide the user id so you will have permission to write
# to /venv/awx
docker exec --user=0 -it tools_awx_1 bash -c "source /venv/awx/bin/activate; pip install /awx_devel/tower-license/"

# Or access the dev container by providing the user id
docker exec --user=0 -it tools_awx_1 bash

# And run below commands
source /venv/awx/bin/activate
pip install awx_devel/tower-license/
exit
```

> Note: when cloning the tower-license repo, you can do so in the container, but will need to use a
[GitHub OAuth key](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/)
because your local ssh credentials will not be accessible from inside the container.



### Run Integration Tests

Note: It is recommended you run Python 3.6.6 if possible to match what is
running on Jenkins.  There are some notable differences between Python 3.6 and
Python 3.7, which is the default python on Fedora 29+. You can install multiple
Python versions on Fedora, see [the
docs](https://developer.fedoraproject.org/tech/languages/python/multiple-pythons.html)
for more information.

```
# navigate to tower-qa on your local file system
exit
cd ../tower-qa

# Tweak the location of the virtualenv to taste
python3.6 -m venv ~/venvs/tower-qa
source ~/venvs/tower-qa/bin/activate
pip install -r requirements.txt
ansible-vault decrypt config/credentials.vault --output=config/credentials.yml    # you will need the vault password
# When running tests using docker ensure that the password and username created previously are present on the credentials.yml file
py.test -c config/docker.cfg
```

> Note: if running tests against a production instance, use:
py.test -c config/api.cfg --base-url='https://<tower-host\>'


### Run Collection tests

Note: It is recommended you run Python 3.6.6 if possible to match what is
running on Jenkins.  There are some notable differences between Python 3.6 and
Python 3.7, which is the default python on Fedora 29+. You can install multiple
Python versions on Fedora, see [the
docs](https://developer.fedoraproject.org/tech/languages/python/multiple-pythons.html)
for more information.

```
# navigate to tower-qa on your local file system
exit
cd ../tower-qa

# Tweak the location of the virtualenv to taste
python3.6 -m venv ~/venvs/tower-qa
source ~/venvs/tower-qa/bin/activate
pip install -r requirements.txt
pip install -r collection-test-requirements.txt
ansible-vault decrypt config/credentials.vault --output=config/credentials.yml    # you will need the vault password
# When running tests using docker ensure that the password and username created previously are present on the credentials.yml file
scripts/install-collection-venv.sh # this installs the virtualenv needed for collection tests in the docker container
scripts/install-collection.sh ../awx # this installs the collection locally and in the docker container
py.test -c config/docker.cfg tests/collection

# Run the sanity tests
cd ~/.ansible/collections/ansible_collections/awx/awx/
ansible-test sanity
```

### Infrastructure dependencies

Some infrastructure is spawned by tests by provisioning services on a kubernetes cluster we have in GCE. Other tests rely on static infrastructure.

This includes, but is not limited to:
  - Azure login + hosts
  - Openstack login + hosts ([docs](https://github.com/ansible/tower-qa/blob/devel/docs/knowledge_base/openstack_config.md)
  - GCE login + hosts
  - EC2 login + hosts


More documentation is needed in this area.

### Using with local awxkit

If you intend to make modifications to awxkit as well, you should pip install awxkit with the `-e`
so that you changes are picked up automatically.
```
cd ~/
git clone git@github.com:ansible/awx.git
# make sure you are in the tower-qa venv, then install awxkit
source ~/venv/tower-qa/bin/activate
pip install -e ~/awx/awxkit/
```

### Rebuilding Fresh Images

Gcloud caches images locally, plus stopping the main awx container (and even a `make docker-clean`) won't remove your current postgres container. To start fresh images, potentially with a new version of awx/tower, requires you to remove all your existing images and refresh your local cache. The following steps, inside your local tower clone directory, achieve this:

```
make clean
make docker-clean
docker rm -f $(docker ps -aq)
docker rmi -f $(docker images -aq)
gcloud docker -- pull gcr.io/ansible-tower-engineering/awx_devel:devel
```

> Note: this will delete _all_ containers and images, not just those related to AWX/Tower.

## Other Helpful Snippets

```bash
# install dependencies
pip install -r requirements.txt

# decrypt credentials
ansible-vault decrypt config/credentials.vault --output=config/credentials.yml

# run api tests
py.test -c config/api.cfg --base-url='https://ec2-tower.com'

# select a subset of tests, with debugger
py.test -c config/api.cfg --base-url='https://ec2-tower.com' -k "test_something" --pdb

# ignore pytest warnings by adding this flag:
--disable-pytest-warnings

# run linter
flake8

# Setting Environment Variables (add before the invocation of pytest on the same command)
AWXKIT_PREVENT_TEARDOWN=1  # bypass teardown
```

# Jupyter

There are some example jupyter notebooks of interacting with tower via awxkit in docs/jupyter.

awxkit
======

awxkit is a library for interacting with [AWX's](https://github.com/ansible/awx) REST API.  It is used by the integration tests at [tower-qa](https://github.com/ansible/tower-qa), drives upgrade and migration testing, and also comes in handy as a scriptable AWX client.


# Cost of Entry
1. AWX instance.
2. Python 3.6 virtual environment (it probably work on Python 3.6+)
3. Recommended: Valid [tower-qa credential file](https://github.com/ansible/tower-qa/blob/master/scripts/create_credentials.py).
4. Recommended: Valid [projects yml file](https://github.com/ansible/tower-qa/blob/devel/config/projects.yml) for creating projects with default scm urls
5. Recommended: [IPython](https://pypi.org/project/ipython/)


# Installation

If you want to just use awxkit, use the following installation procedure:

```
python3.6 -m venv venv
source venv/bin/activate
pip install -U "git+ssh://git@github.com/ansible/awx.git#egg=awxkit[websockets]&subdirectory=awxkit"
```

If you planning to contribute to awxkit, use the below installation
procedure:

```
$ git clone https://github.com/ansible/awx.git
$ cd awx/awxkit
$ python3.6 -m venv ~/venv
$ source ~/venv/bin/activate
$ pip install -e .
``````

The above commands will clone the repository and install awxkit in editable
mode, which is good for development.

# Basic Usage
awxkit's interface was designed to blend web crawling and AWX API usage.  It is accessible as a standard python package, but will likely be most helpful in a python repl via `akit`:

```bash
whoiam$ AWXKIT_USER=username AWXKIT_USER_PASSWORD=password AWXKIT_BASE_URL=https://${AWX_HOST} akit -c path/to/credentials.yml -p path/to/projects.yml
```
This will load a basic user session as the specified user on the target system.  Immediately accessible are two page objects `root` and `v2`:

```python
In [1]: root
Out[1]:
{
    "available_versions": {
        "v2": "/api/v2/"
    },
    "oauth2": "/api/o/",
    "description": "AWX REST API",
    "custom_login_info": "",
    "current_version": "/api/v2/",
    "custom_logo": ""
}

In [3]: v2
Out[3]:
{
    "job_templates": "/api/v2/job_templates/",
    "job_events": "/api/v2/job_events/",
    "inventory_scripts": "/api/v2/inventory_scripts/",
    "labels": "/api/v2/labels/",
    "schedules": "/api/v2/schedules/",
    "workflow_job_nodes": "/api/v2/workflow_job_nodes/",
    "instances": "/api/v2/instances/",
    "instance_groups": "/api/v2/instance_groups/",
    "credential_types": "/api/v2/credential_types/",
    "teams": "/api/v2/teams/",
    "inventory_updates": "/api/v2/inventory_updates/",
    "system_jobs": "/api/v2/system_jobs/",
    "workflow_jobs": "/api/v2/workflow_jobs/",
    "ad_hoc_commands": "/api/v2/ad_hoc_commands/",
    "project_updates": "/api/v2/project_updates/",
    "ping": "/api/v2/ping/",
    "inventory": "/api/v2/inventories/",
    "config": "/api/v2/config/",
    "inventory_sources": "/api/v2/inventory_sources/",
    "jobs": "/api/v2/jobs/",
    "users": "/api/v2/users/",
    "organizations": "/api/v2/organizations/",
    "notification_templates": "/api/v2/notification_templates/",
    "tokens": "/api/v2/tokens/",
    "unified_jobs": "/api/v2/unified_jobs/",
    "applications": "/api/v2/applications/",
    "groups": "/api/v2/groups/",
    "unified_job_templates": "/api/v2/unified_job_templates/",
    "credentials": "/api/v2/credentials/",
    "workflow_job_template_nodes": "/api/v2/workflow_job_template_nodes/",
    "projects": "/api/v2/projects/",
    "me": "/api/v2/me/",
    "workflow_job_templates": "/api/v2/workflow_job_templates/",
    "roles": "/api/v2/roles/",
    "notifications": "/api/v2/notifications/",
    "settings": "/api/v2/settings/",
    "system_job_templates": "/api/v2/system_job_templates/",
    "hosts": "/api/v2/hosts/",
    "dashboard": "/api/v2/dashboard/",
    "activity_stream": "/api/v2/activity_stream/"
}
```

All page views in awxkit operate with the same fluent REST interface:

```python
In [4]: me_list = v2.me.get()
Out[4]:
{
    "count": 1,
    "next": null,
    "results": [
        {
            "username": "admin",
            "first_name": "",
            "last_name": "",
            "created": "2018-03-05T14:30:00.985980Z",
            "url": "/api/v2/users/1/",
            "summary_fields": {
                "user_capabilities": {
                    "edit": true,
                    "delete": false
                }
            },
            "ldap_dn": "",
            "external_account": null,
            "related": {
                "admin_of_organizations": "/api/v2/users/1/admin_of_organizations/",
                "authorized_tokens": "/api/v2/users/1/authorized_tokens/",
                "roles": "/api/v2/users/1/roles/",
                "organizations": "/api/v2/users/1/organizations/",
                "access_list": "/api/v2/users/1/access_list/",
                "teams": "/api/v2/users/1/teams/",
                "tokens": "/api/v2/users/1/tokens/",
                "applications": "/api/v2/users/1/applications/",
                "personal_tokens": "/api/v2/users/1/personal_tokens/",
                "credentials": "/api/v2/users/1/credentials/",
                "activity_stream": "/api/v2/users/1/activity_stream/",
                "projects": "/api/v2/users/1/projects/"
            },
            "id": 1,
            "is_superuser": true,
            "auth": [],
            "is_system_auditor": false,
            "type": "user",
            "email": "admin@example.com"
        }
    ],
    "previous": null
}
In [5]: me = me_list.results.pop().get()

In [6]: me.username
Out[6]: u'admin
In [7]: me.first_name = "MyNewFirstName"  # This is a PATCH.  POST/PUT/OPTIONS/HEAD/DELETE are all provided as well

In [8]: me.get().first_name
Out[8]: u'MyNewFirstName'
```

`akit` can also run scripts for easy system configuration:

```bash
whoiam$ cat some_script
print v2.me.get().results.pop().username
whoiam$ akit -f some_script -x // -x causes akit to exit when finished
admin
whoiam$
```

## Debugging

If you want to see each call logged, set in your environment `AWXKIT_DEBUG=1` or `AWXKIT_DEBUG=true`.
Then you will see things like:
```
DEBUG:urllib3.connectionpool:http://127.0.0.1:8013 "GET /api/ HTTP/1.1" 200 157
DEBUG:awxkit.api.client:"GET http://127.0.0.1:8013/api/" elapsed: 0:00:00.034390
DEBUG:awxkit.api.registry:Retrieved <class 'awxkit.api.pages.api.ApiV2'> by url: /api/v2/
DEBUG:urllib3.connectionpool:http://127.0.0.1:8013 "GET /api/v2/ HTTP/1.1" 200 1637
DEBUG:awxkit.api.client:"GET http://127.0.0.1:8013/api/v2/" elapsed: 0:00:00.037606
```
When you run a command line interactive session.
