from fauxfactory import gen_boolean, gen_alpha, gen_choice
from awxkit.utils import poll_until
from awxkit.exceptions import NoContent
import pytest

from tests.api import APITest
from tests.lib.helpers.copy_utils import check_fields

from tests.api.workflows.utils import (
    get_job_node,
    get_job_status,
)
from tests.lib.helpers.workflow_utils import (WorkflowTree, WorkflowTreeMapper)


@pytest.mark.usefixtures('authtoken')
class Test_Copy_Workflow_Job_Template(APITest):

    identical_fields = ['type', 'description', 'extra_vars', 'organization', 'survey_enabled', 'allow_simultaneous',
                        'ask_variables_on_launch']
    unequal_fields = ['id', 'created', 'modified']

    def check_node_fields(self, old_node, new_node, old_wfjt, new_wfjt):
        identical_fields = ['type', 'extra_data', 'job_type', 'job_tags', 'skip_tags', 'limit', 'diff_mode',
                            'verbosity']
        unequal_fields = ['id', 'created', 'modified']

        assert old_node.workflow_job_template == old_wfjt.id
        assert new_node.workflow_job_template == new_wfjt.id
        check_fields(old_node, new_node, identical_fields, unequal_fields)

    def add_child_node(self, endpoint, node):
        endpoint.connection.post(endpoint.endpoint, dict(id=node.id))

    def get_node_children(self, node, indexed_nodes):
        children = []
        children += [indexed_nodes[i] for i in node.success_nodes]
        children += [indexed_nodes[i] for i in node.failure_nodes]
        children += [indexed_nodes[i] for i in node.always_nodes]
        return children

    def get_root_nodes(self, indexed_nodes):
        roots = dict(indexed_nodes)
        for node in indexed_nodes.values():
            for child in self.get_node_children(node, indexed_nodes):
                for nid in roots:
                    if nid == child.id:
                        roots.pop(nid)
                        break

        return list(roots.values())

    def create_wfjt_with_nodes(self, v2, factories, num_nodes):
        post_options = v2.workflow_job_template_nodes.options().actions.POST
        job_types = list(dict(post_options.job_type.choices).keys())
        verbosities = list(dict(post_options.verbosity.choices).keys())
        wfjt = factories.workflow_job_template()
        nodes = []
        for i in range(4):
            jt = factories.job_template(ask_variables_on_launch=gen_boolean(), ask_job_type_on_launch=gen_boolean(),
                                           ask_tags_on_launch=gen_boolean(), ask_skip_tags_on_launch=gen_boolean(),
                                           ask_limit_on_launch=gen_boolean(), ask_verbosity_on_launch=gen_boolean(),
                                           ask_diff_mode_on_launch=gen_boolean())
            extra_data = '{"foo": "bar"}' if jt.ask_variables_on_launch else ''
            job_type = gen_choice(job_types) if jt.ask_job_type_on_launch else None
            job_tags = gen_alpha() if jt.ask_tags_on_launch else None
            skip_tags = gen_alpha() if jt.ask_skip_tags_on_launch else None
            limit = gen_alpha() if jt.ask_limit_on_launch else None
            verbosity = gen_choice(verbosities) if jt.ask_verbosity_on_launch else None
            diff_mode = gen_boolean() if jt.ask_diff_mode_on_launch else None
            nodes.append(factories.workflow_job_template_node(workflow_job_template=wfjt, extra_data=extra_data,
                                                                 job_type=job_type, job_tags=job_tags,
                                                                 skip_tags=skip_tags, limit=limit, verbosity=verbosity,
                                                                 diff_mode=diff_mode, unified_job_template=jt))
        return wfjt

    def test_copy_normal(self, factories, copy_with_teardown):
        wfjt = factories.workflow_job_template()
        new_wfjt = copy_with_teardown(wfjt)
        check_fields(wfjt, new_wfjt, self.identical_fields, self.unequal_fields)

    def test_copy_wfjt_with_non_default_values(self, factories, copy_with_teardown):
        wfjt = factories.workflow_job_template(extra_vars='{"foo": "bar"}', survey_enabled=gen_boolean(),
                                                  allow_simultaneous=gen_boolean(),
                                                  ask_variables_on_launch=gen_boolean())
        new_wfjt = copy_with_teardown(wfjt)
        check_fields(wfjt, new_wfjt, self.identical_fields, self.unequal_fields)

    def test_copy_wfjt_labels(self, factories, copy_with_teardown):
        wfjt = factories.workflow_job_template()
        label = factories.label()
        wfjt.add_label(label)
        new_wfjt = copy_with_teardown(wfjt)

        old_labels = wfjt.related.labels.get()
        new_labels = new_wfjt.related.labels.get()

        check_fields(wfjt, new_wfjt, self.identical_fields, self.unequal_fields)
        assert old_labels.count == 1
        assert new_labels.count == old_labels.count
        assert new_labels.results[0].id == old_labels.results[0].id

    def test_copy_wfjt_survey_spec(self, factories, copy_with_teardown):
        wfjt = factories.workflow_job_template()
        survey = [dict(required=False,
                       question_name='Test-1',
                       variable='var1',
                       type='password',
                       default='var1_default')]
        wfjt.add_survey(spec=survey)
        new_wfjt = copy_with_teardown(wfjt)

        old_survey = wfjt.related.survey_spec.get().json
        new_survey = new_wfjt.related.survey_spec.get().json

        check_fields(wfjt, new_wfjt, self.identical_fields, self.unequal_fields)
        assert new_survey == old_survey

    @pytest.mark.yolo
    def test_copy_wfjt_nodes(self, v2, factories, copy_with_teardown):
        # Create a forest of wfjt nodes
        wfjt = self.create_wfjt_with_nodes(v2, factories, num_nodes=4)
        wfjt_nodes_pg = wfjt.related.workflow_nodes.get()
        assert wfjt_nodes_pg.count == 4

        nodes = wfjt_nodes_pg.results
        self.add_child_node(nodes[0].related.success_nodes, nodes[1])
        self.add_child_node(nodes[0].related.failure_nodes, nodes[2])
        self.add_child_node(nodes[1].related.always_nodes, nodes[3])

        # Make a copy
        old_wfjt = wfjt
        new_wfjt = copy_with_teardown(wfjt)
        check_fields(old_wfjt, new_wfjt, self.identical_fields, self.unequal_fields)
        poll_until(lambda: new_wfjt.related.workflow_nodes.get().count == wfjt_nodes_pg.count, timeout=30)

        # Traverse & compare the two graphs
        old_nodes = dict([(n.id, n) for n in wfjt_nodes_pg.get().results])
        new_nodes = dict([(n.id, n) for n in new_wfjt.related.workflow_nodes.get().results])
        assert len(old_nodes) == len(new_nodes)

        old_frontier = sorted(self.get_root_nodes(old_nodes), key=lambda n: n.unified_job_template)
        new_frontier = sorted(self.get_root_nodes(new_nodes), key=lambda n: n.unified_job_template)
        assert len(old_frontier) == len(new_frontier)
        while old_frontier:
            old_node = old_frontier.pop()
            new_node = new_frontier.pop()
            assert old_node.unified_job_template == new_node.unified_job_template
            self.check_node_fields(old_node, new_node, old_wfjt, new_wfjt)

            old_frontier.extend(sorted(self.get_node_children(old_node, old_nodes), key=lambda n: n.unified_job_template))
            new_frontier.extend(sorted(self.get_node_children(new_node, new_nodes), key=lambda n: n.unified_job_template))
        assert not new_frontier

    def test_copy_wfjt_with_approval_node(self, v2, factories, org_admin, copy_with_teardown):
        """Create a workflow with an approval node and copy it."""
        org = org_admin.related.organizations.get().results.pop()
        wfjt = factories.workflow_job_template(organization=org)
        org_auditor = factories.user(organization=org)
        wf_read_user = factories.user(organization=org)
        org.set_object_roles(org_auditor, 'auditor')
        wfjt.set_object_roles(wf_read_user, 'read')
        factories.workflow_job_template_node(
            workflow_job_template=wfjt,
            unified_job_template=None
        ).make_approval_node()
        wfjt_copy = copy_with_teardown(wfjt)
        old_workflow_approval_template = wfjt.related.workflow_nodes.get().results.pop().related.unified_job_template.get()
        new_workflow_approval_template = wfjt_copy.related.workflow_nodes.get().results.pop().related.unified_job_template.get()
        assert old_workflow_approval_template.id != new_workflow_approval_template.id
        assert new_workflow_approval_template.type == "workflow_approval_template"
        wfjt.delete()
        with self.current_user(org_auditor.username, org_auditor.password):
            assert v2.workflow_job_templates.get(id=wfjt_copy.id).count == 1
        with self.current_user(wf_read_user.username, wf_read_user.password):
            assert v2.workflow_job_templates.get(id=wfjt_copy.id).count == 0

    def test_copy_wfjt_with_convergence_node(self, factories, copy_with_teardown):
        """Create a workflow with a convergence and copy it to verify if the convergence property is preserved."""
        host = factories.host()
        wfjt = factories.workflow_job_template()
        jt_success_1 = factories.job_template(
            inventory=host.ds.inventory,
            allow_simultaneous=True)
        jt_failure = factories.job_template(
            inventory=host.ds.inventory,
            allow_simultaneous=True,
            playbook='fail_unless.yml')
        jt_success_2 = factories.job_template(
            inventory=host.ds.inventory,
            allow_simultaneous=True)
        n1_success = factories.workflow_job_template_node(
            workflow_job_template=wfjt, unified_job_template=jt_success_1)
        n2_failure = factories.workflow_job_template_node(
            workflow_job_template=wfjt, unified_job_template=jt_failure)
        convergence_node = factories.workflow_job_template_node(
            workflow_job_template=wfjt, unified_job_template=jt_success_2, all_parents_must_converge=True)
        with pytest.raises(NoContent):
            n1_success.related.success_nodes.post(dict(id=convergence_node.id))
        with pytest.raises(NoContent):
            n2_failure.related.success_nodes.post(dict(id=convergence_node.id))
        # Run the job
        wfj = wfjt.launch().wait_until_completed()
        tree = WorkflowTree(wfjt)
        job_tree = WorkflowTree(wfj)
        mapping = WorkflowTreeMapper(tree, job_tree).map()
        convergence_workflow_job_node = get_job_node(wfj, convergence_node.id, mapping)

        # Assert each job reached expected states
        assert 'successful' == get_job_status(wfj, n1_success.id, mapping)
        assert 'failed' == get_job_status(wfj, n2_failure.id, mapping)
        assert convergence_workflow_job_node.do_not_run

        # Make a copy and assert that the convergence property is preserved
        wfjt_copy = copy_with_teardown(wfjt)

        # Run the job from copy wfjt
        wfj_copy = wfjt_copy.launch().wait_until_completed()
        tree_copy = WorkflowTree(wfjt_copy)
        job_tree_copy = WorkflowTree(wfj_copy)
        mapping_copy = WorkflowTreeMapper(tree_copy, job_tree_copy).map()
        n1_success_copy = wfjt_copy.related.workflow_nodes.get(unified_job_template=jt_success_1.id).results.pop()
        n2_failure_copy = wfjt_copy.related.workflow_nodes.get(unified_job_template=jt_failure.id).results.pop()
        convergence_node_copy = wfjt_copy.related.workflow_nodes.get(unified_job_template=jt_success_2.id).results.pop()
        convergence_workflow_job_node_copy = get_job_node(wfj_copy, convergence_node_copy.id, mapping_copy)

        # Assert each job reached expected states
        assert 'successful' == get_job_status(wfj_copy, n1_success_copy.id, mapping_copy)
        assert 'failed' == get_job_status(wfj_copy, n2_failure_copy.id, mapping_copy)
        assert convergence_workflow_job_node_copy.do_not_run
