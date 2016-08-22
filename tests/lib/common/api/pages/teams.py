import fauxfactory

from common.api import resources
import base


class Team(base.Base):

    def add_permission(self, permission_type, project=None, inventory=None, run_ad_hoc_commands=None):
        perm_pg = self.get_related('permissions')
        payload = dict(name=fauxfactory.gen_utf8(),
                       description=fauxfactory.gen_utf8(),
                       user=self.id,
                       permission_type=permission_type,
                       project=project,
                       inventory=inventory,
                       run_ad_hoc_commands=run_ad_hoc_commands)
        result = perm_pg.post(payload)
        return result

base.register_page(resources.v1_team, Team)


class Teams(Team, base.BaseList):

    pass

base.register_page([resources.v1_teams,
                    resources.v1_related_teams], Teams)

# backwards compatibility
Team_Page = Team
Teams_Page = Teams
