# Tower-QA

Hello! Excited to have you join us.

If you have any questions about this document, reach out to the team on the `ship_it` channel in slack.
If you have any updates, make a PR!

## Getting ansible/tower-qa

`ansible/tower-qa` is a private GitHub repository. Please make sure you are part of the Ansible Org on GitHub to be able to clone it.

To clone it locally run:

```
#> git clone git@github.com:ansible/tower-qa.git
#> virtualenv /path/to/virtualenv && source /path/to/virtualenv/bin/activate
#> cd tower-qa && pip install -r requirements.txt
#> pip install -U "git+ssh://git@github.com/ansible/awx.git@devel#egg=awxkit[websockets]&subdirectory=awxkit"
```

Whenever you submit a contribution to `ansible/tower-qa` it will go through some CI testing for lint.
While this happens on our Jenkins, you can make sure your contribution (your commit) passes locally before even sending the pull request.

For this to happen, please run the following command:

```
#> git config core.hooksPath hooks
```

Now everytime you will commit something, you should observe a similar output:

```
Starting commit sanity checking ...

[tox] Ensuring tox passes... Success
[whitespace] Ensure no whitespace are present... Success

[yamllint d03113c21] hooks: Add pre-commit hook
 Date: Wed Oct 16 15:47:53 2019 +0200
 2 files changed, 69 insertions(+), 1 deletion(-)
 create mode 100755 hooks/pre-commit
```

You are now all set to start contributing ! Happy Hacking !


## Branching strategy
## Feature Test Branches

When working on a feature with a developer, create a branch based off of master
for the feature. For this example, we will call our feature, `feature-123`. Say
there are two testers and one developer working on this feature, named:
* `cow`
* `moose`
* `ant`

Then they would each create branches named
* `cow-feature-123`
* `moose-feature-123`
* `and-feature-123`.

As they write tests, they make PRs against `feature-123`. This allows them to
move fast and get reviews on small changes, and it makes it clear what the new
changes are that need reviewed instead of having one branch they all hammer
against and where the PR history grows as the branch may live for the entire
duration of the sprint, or even longer if it is a larger feature.

You may like to intermittently rebase `feature-123` off of master and then your
personal branch `cow-feature-123` off of `feature-123` to keep up with changes
in master.

When the feature is complete, then the tester can make the final PR of
`feature-123` against master. If any commit squashing needs to happen to make a
sensible history, this can be done at this time.

## Release Branches

`ansible/tower-qa` follows the same branching convention as `ansible/tower`.

Main development branch of `ansible/tower-qa` is `devel`.
Then each minor releases have their own branch `release_3.3.1`, `release_3.2.8`, etc...
As soon as a new minor release is actually released a new branch is created `release X.Y.z+1`.

When making a PR to `ansible/tower-qa` please think about if this
contribution makes sense to be backported to currently active release
branches.


## Running tests locally

As a contributor, you can run part of the tests suite run by Jenkins locally.

In order to do so, you need to have `tox` installed.

Then at the root of this repository simply run `tox`


## Techdebt and upgrades

Please file issues in the libraries we depend on if version changes
break our usage or if deprecation warnings are emitted.

If our own usage is causing deprecation warnings to show in test runs locally
or on Jenkins, file an issue in the applicable project.

PRs to delete dead code or update stale code are always welcome! :)

## Maintaining compatiblity with old versions of tower-qa and towerkit

Our jenkins jobs are used to run various versions of the project. For
this reason, we need to maintain the ability to run the jobs for old and
new versions.

This means we should keep requirements under source control in the
project itself. There are still some requirements hiding out in various
jenkins jobs, feel free to refactor.

We also need to detect the version of python supported by the branch we
are running.

The current best practice for doing this, since the current Jenkins
infrastructure uses python2 as the system python, is to look for `python3`
in the `tox.ini` file and create a virtual environment if it is found.

Example:

```
# Enable python3 if this version of tower-qa uses it
if [ "$(grep -s "python3" tox.ini)" ]; then
python3 -m venv $PWD/venv
source $PWD/venv/bin/activate
fi
```

This should happen before pip installing anything.
