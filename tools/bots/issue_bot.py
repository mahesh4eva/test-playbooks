#!/usr/bin/env python

import os
import requests

from slacker import Slacker


github_token = os.getenv('GITHUB_TOKEN')
tower_version = os.getenv('TOWER_VERSION')

slack_token = os.getenv('SLACK_TOKEN')
slack_channel = os.getenv('SLACK_CHANNEL')
slack = Slacker(slack_token)

API_GITHUB = 'https://api.github.com'


def github_request(url):

    res = requests.get(
        url,
        headers={
            'Authorization': 'token %s' % github_token,
            'Accept': 'application/vnd.github.inertia-preview+json'
        }
    )

    return res


def get_project_id_and_number_for_a_tower_version(version):

    url = '{}/orgs/ansible/projects'.format(API_GITHUB)
    projects = github_request(url).json()

    return [(project['id'], project['number']) for project in projects if project['name'] == 'Ansible Tower {}'.format(version)][0]


def get_issues_content_from_column(url, index=1, issues=[]):
    """Recursive method to iterate over pages to retrieve all issues from columns"""

    _issues = []
    for _issue in github_request('%s?page=%s' % (url, index)).json():
        if 'content_url' in _issue:
            _issues.append(github_request(_issue['content_url']).json())

    issues = issues + _issues
    if len(_issues) == 30:
        return get_issues_content_from_column(url, index + 1, issues)

    return issues


def get_open_issues_from_project(project_id):

    _issues = []
    # Retrieve list of cards_url
    url = '{}/projects/{}/columns'.format(API_GITHUB, project_id)

    _columns = github_request(url).json()
    cards_url = [column['cards_url'] for column in _columns if 'QE' not in column['name'] and 'Done' != column['name']]

    for url in cards_url:
        _issues += get_issues_content_from_column(url)

    return [issue for issue in _issues if issue['state'] == 'open']


def is_issue_in_need_test(issue):

    for label in issue['labels']:
        if label['name'] == 'state:needs_test':
            return True

    return False


def is_issue_assigned(issue):

    team_members = ['elyezer', 'Spredzy', 'kdelee',
                    'one-t', 'dsesami', 'unlikelyzero',
                    'appuk', 'squidboylan']

    assignees = [mate['login'] for mate in issue['assignees']]

    if set(assignees) - set(team_members) == set(assignees):
        return False

    return True


def post_slack_msg(text):
    slack.chat.post_message(slack_channel, text, icon_emoji=':ansible:')


def create_issue_update():

    project_id, project_number = get_project_id_and_number_for_a_tower_version(tower_version)
    issues = get_open_issues_from_project(project_id)

    needs_test = []
    for issue in issues:
        if is_issue_in_need_test(issue):
            issue['assigned'] = is_issue_assigned(issue)
            needs_test.append(issue)

    unassigned_api, unassigned_ui, unassigned_ui_next = 0, 0, 0
    for issue in needs_test:
        if not issue['assigned']:
            labels = [label['name'] for label in issue['labels']]
            if 'component:api' in labels:
                unassigned_api += 1
            if 'component:ui' in labels:
                unassigned_ui += 1
            if 'component:ui_next' in labels:
                unassigned_ui_next += 1

    extra_msg = ''
    if unassigned_api or unassigned_ui or unassigned_ui_next:
        extra_msg = " | {} API and {} UI and {} ui_next issues are in needs_test and unassigned, @qe please assign yourselves".format(
            unassigned_api, unassigned_ui, unassigned_ui_next
        )

    url = 'https://github.com/issues?q=is:open+is:issue+project:ansible/{}'.format(
        project_number
    )
    return "{} open issues in project `{}` ({} in `state:needs_test`{}) - Link: {}".format(
        len(issues), tower_version, len(needs_test), extra_msg, url
    )


post_slack_msg(create_issue_update())

if __name__ == '__main__':
    create_issue_update()
