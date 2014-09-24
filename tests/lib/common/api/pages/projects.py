import time
import common.utils
from common.api.pages import Base, Base_List, Task_Page, json_getter, json_setter


class Project_Page(Base):
    base_url = '/api/v1/projects/{id}/'
    name = property(json_getter('name'), json_setter('name'))
    description = property(json_getter('description'), json_setter('description'))
    status = property(json_getter('status'), json_setter('status'))
    local_path = property(json_getter('local_path'), json_setter('local_path'))
    last_updated = property(json_getter('last_updated'), json_setter('last_updated'))
    last_update_failed = property(json_getter('last_update_failed'), json_setter('last_update_failed'))
    last_job_run = property(json_getter('last_job_run'), json_setter('last_job_run'))
    last_job_failed = property(json_getter('last_job_failed'), json_setter('last_job_failed'))
    scm_type = property(json_getter('scm_type'), json_setter('scm_type'))
    scm_url = property(json_getter('scm_url'), json_setter('scm_url'))
    scm_branch = property(json_getter('scm_branch'), json_setter('scm_branch'))
    scm_clean = property(json_getter('scm_clean'), json_setter('scm_clean'))
    scm_delete_on_next_update = property(json_getter('scm_delete_on_next_update'), json_setter('scm_delete_on_next_update'))
    scm_update_on_launch = property(json_getter('scm_update_on_launch'), json_setter('scm_update_on_launch'))
    scm_update_cache_timeout = property(json_getter('scm_update_cache_timeout'), json_setter('scm_update_cache_timeout'))

    def get_related(self, name, **kwargs):
        assert name in self.json['related']
        if name == 'last_update':
            related = Project_Update_Page(self.testsetup, base_url=self.json['related'][name])
        elif name == 'current_update':
            related = Project_Update_Page(self.testsetup, base_url=self.json['related'][name])
        elif name == 'project_updates':
            related = Project_Updates_Page(self.testsetup, base_url=self.json['related'][name])
        elif name == 'update':
            related = Base(self.testsetup, base_url=self.json['related'][name])
        elif name == 'playbooks':
            related = Playbooks_Page(self.testsetup, base_url=self.json['related'][name], objectify=False)
        elif name == 'organizations':
            from organizations import Organizations_Page
            related = Organizations_Page(self.testsetup, base_url=self.json['related'][name])
        elif name == 'teams':
            from teams import Teams_Page
            related = Teams_Page(self.testsetup, base_url=self.json['related'][name])
        elif name == 'schedules':
            from schedules import Schedules_Page
            related = Schedules_Page(self.testsetup, base_url=self.json['related'][name])
        else:
            raise NotImplementedError
        return related.get(**kwargs)

    def wait_until_started(self, interval=1, verbose=0, timeout=60):
        '''Wait until a project_update has started'''
        return common.utils.wait_until(
            self, 'status',
            ('new', 'pending', 'waiting', 'running',),
            interval=interval, verbose=verbose, timeout=timeout)

    def wait_until_completed(self, interval=5, verbose=0, timeout=60 * 8):
        return common.utils.wait_until(
            self, 'status',
            ('successful', 'failed', 'error', 'canceled',),
            interval=interval, verbose=verbose, timeout=timeout)

class Projects_Page(Project_Page, Base_List):
    base_url = '/api/v1/projects/'


class Project_Update_Page(Task_Page):
    base_url = '/api/v1/project/{id}/update/'


class Project_Updates_Page(Project_Update_Page, Base_List):
    base_url = '/api/v1/projects/{id}/project_updates/'


class Playbooks_Page(Base):
    base_url = '/api/v1/projects/{id}/playbooks/'
