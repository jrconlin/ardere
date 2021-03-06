import json
import os
import time
import unittest
import uuid

import mock
from botocore.exceptions import ClientError
from nose.tools import eq_, assert_raises

from tests import fixtures


class TestAsyncPlanRunner(unittest.TestCase):
    def setUp(self):
        self.mock_ecs = mock.Mock()
        self._patcher = mock.patch("ardere.step_functions.ECSManager")
        mock_manager = self._patcher.start()
        mock_manager.return_value = self.mock_ecs

        from ardere.step_functions import AsynchronousPlanRunner

        self.plan = json.loads(fixtures.sample_basic_test_plan)
        self.runner = AsynchronousPlanRunner(self.plan, {})
        self.runner.boto = self.mock_boto = mock.Mock()

    def tearDown(self):
        self._patcher.stop()

    def test_build_instance_map(self):
        result = self.runner._build_instance_map()
        eq_(len(result), 1)
        eq_(result, {"t2.medium": 1})

    def test_find_test_plan_duration(self):
        result = self.runner._find_test_plan_duration()
        eq_(result, 140)

    def test_load_toml(self):
        from ardere.step_functions import AsynchronousPlanRunner

        self.runner = AsynchronousPlanRunner({"toml": fixtures.sample_toml},
                                             None)
        eq_(len(self.runner.event["steps"]), 2)
        eq_(self.runner.event["steps"][0]["instance_count"], 8)
        eq_(self.runner.event["ecs_name"], "ardere-test")

    def test_populate_missing_instances(self):
        os.environ["ec2_sg"] = "i-23232"
        os.environ["metric_sg"] = "i-84828"
        self.mock_ecs.has_metrics_node.return_value = False
        self.runner.populate_missing_instances()
        self.mock_ecs.query_active_instances.assert_called()
        self.mock_ecs.request_instances.assert_called()

    def test_populate_missing_instances_fail(self):
        from ardere.exceptions import ValidationException
        mock_client = mock.Mock()
        self.mock_boto.client.return_value = mock_client
        mock_client.describe_clusters.return_value = {"clusters": []}
        assert_raises(ValidationException,
                      self.runner.populate_missing_instances)

    def test_ensure_metrics_available_running_create(self):
        from ardere.exceptions import ServicesStartingException

        self.plan["metrics_options"] = dict(enabled=True)
        self.mock_ecs.locate_metrics_service.return_value = None

        assert_raises(ServicesStartingException,
                      self.runner.ensure_metrics_available)
        self.mock_ecs.create_metrics_service.assert_called()

    def test_ensure_metrics_available_running_waiting(self):
        from ardere.exceptions import ServicesStartingException

        self.plan["metrics_options"] = dict(enabled=True)
        self.mock_ecs.locate_metrics_service.return_value = {
            "deployments": [{
                "desiredCount": 1,
                "runningCount": 0
            }]
        }

        assert_raises(ServicesStartingException,
                      self.runner.ensure_metrics_available)

    def test_ensure_metrics_available_running_error(self):
        self.plan["metrics_options"] = dict(enabled=True)
        self.mock_ecs.locate_metrics_service.return_value = {
            "deployments": [{
                "desiredCount": 1,
                "runningCount": 1
            }]
        }
        self.mock_ecs.locate_metrics_container_ip.return_value = None

        assert_raises(Exception, self.runner.ensure_metrics_available)

    def test_ensure_metrics_available_running(self):
        os.environ["metrics_bucket"] = "metrics"
        self.plan["metrics_options"] = dict(
            enabled=True,
            dashboard=dict(admin_user="admin",
                           admin_password="admin", name="fred",
                           filename="smith")
        )
        self.mock_ecs.locate_metrics_service.return_value = {
            "deployments": [{
                "desiredCount": 1,
                "runningCount": 1
            }]
        }
        self.mock_ecs.locate_metrics_container_ip.return_value = (
            "1.1.1.1", "arn:::"
        )

        self.runner.ensure_metrics_available()
        self.mock_ecs.locate_metrics_container_ip.assert_called()

    def test_ensure_metrics_available_running_no_metric_ip(self):
        os.environ["metrics_bucket"] = "metrics"
        self.plan["metrics_options"] = dict(
            enabled=True,
            dashboard=dict(admin_user="admin",
                           admin_password="admin", name="fred",
                           filename="smith")
        )
        self.mock_ecs.locate_metrics_service.return_value = {
            "deployments": [{
                "desiredCount": 1,
                "runningCount": 1
            }]
        }
        self.mock_ecs.locate_metrics_container_ip.return_value = (
            None, None
        )

        assert_raises(Exception, self.runner.ensure_metrics_available)
        self.mock_ecs.locate_metrics_container_ip.assert_called()

    def test_ensure_metrics_available_disabled(self):
        self.plan["metrics_options"] = dict(enabled=False)
        self.runner.ensure_metrics_available()

    def test_ensure_metric_sources_created(self):
        os.environ["metrics_bucket"] = "metrics"
        self.plan["influxdb_private_ip"] = "1.1.1.1"
        self.plan["metrics_options"] = dict(
            enabled=True,
            dashboard=dict()
        )
        self.mock_ecs.has_started_metric_creation.return_value = True
        self.runner.ensure_metric_sources_created()
        self.mock_ecs.has_started_metric_creation.assert_called()

    def test_ensure_metric_sources_created_not_finished(self):
        from ardere.exceptions import CreatingMetricSourceException
        os.environ["metrics_bucket"] = "metrics"
        self.plan["influxdb_private_ip"] = "1.1.1.1"
        self.plan["metrics_options"] = dict(
            enabled=True,
        )
        self.mock_ecs.has_started_metric_creation.return_value = True
        self.mock_ecs.has_finished_metric_creation.return_value = False
        assert_raises(CreatingMetricSourceException,
                      self.runner.ensure_metric_sources_created)
        self.mock_ecs.has_started_metric_creation.assert_called()

    def test_ensure_metric_sources_created_not_enabled(self):
        self.plan["metrics_options"] = dict(
            enabled=False,
            dashboard=dict()
        )
        self.runner.ensure_metric_sources_created()

    def test_ensure_metric_sources_created_not_started(self):
        from ardere.exceptions import CreatingMetricSourceException
        os.environ["metrics_bucket"] = "metrics"
        self.plan["influxdb_private_ip"] = "1.1.1.1"
        self.plan["metric_container_arn"] = "arn:::"
        self.plan["metrics_options"] = dict(
            enabled=True,
            dashboard=dict(
                admin_user="admin",
                admin_password="admin",
                filename="asdf",
                name="a title"
            )
        )
        self.mock_ecs.has_started_metric_creation.return_value = False
        assert_raises(CreatingMetricSourceException,
                      self.runner.ensure_metric_sources_created)
        self.mock_ecs.has_started_metric_creation.assert_called()

    def test_ensure_metric_sources_created_not_started_no_dash(self):
        from ardere.exceptions import CreatingMetricSourceException
        os.environ["metrics_bucket"] = "metrics"
        self.plan["influxdb_private_ip"] = "1.1.1.1"
        self.plan["metric_container_arn"] = "arn:::"
        self.plan["metrics_options"] = dict(
            enabled=True,
        )
        self.mock_ecs.has_started_metric_creation.return_value = False
        assert_raises(CreatingMetricSourceException,
                      self.runner.ensure_metric_sources_created)
        self.mock_ecs.has_started_metric_creation.assert_called()

    def test_create_ecs_services(self):
        self.runner.create_ecs_services()
        self.mock_ecs.create_services.assert_called_with(self.plan["steps"])

    def test_wait_for_cluster_ready_not_ready(self):
        from ardere.exceptions import ServicesStartingException

        self.mock_ecs.all_services_ready.return_value = False
        assert_raises(ServicesStartingException,
                      self.runner.wait_for_cluster_ready)

    def test_wait_for_cluster_ready_all_ready(self):
        self.mock_ecs.all_services_ready.return_value = True
        self.runner.wait_for_cluster_ready()
        self.mock_ecs.all_services_ready.assert_called()

    def test_signal_cluster_start(self):
        self.plan["plan_run_uuid"] = str(uuid.uuid4())

        self.runner.signal_cluster_start()
        self.mock_boto.client.assert_called()

    def test_check_for_cluster_done_not_done(self):
        os.environ["s3_ready_bucket"] = "test_bucket"
        mock_file = mock.Mock()
        mock_file.get.return_value = {"Body": mock_file}
        mock_file.read.return_value = "{}".format(
            int(time.time()) - 100).encode(
            'utf-8')
        mock_s3_obj = mock.Mock()
        mock_s3_obj.Object.return_value = mock_file
        self.mock_boto.resource.return_value = mock_s3_obj

        self.plan["plan_run_uuid"] = str(uuid.uuid4())
        self.runner.check_for_cluster_done()

    def test_check_for_cluster_done_shutdown(self):
        from ardere.exceptions import ShutdownPlanException

        os.environ["s3_ready_bucket"] = "test_bucket"
        mock_file = mock.Mock()
        mock_file.get.return_value = {"Body": mock_file}
        mock_file.read.return_value = "{}".format(
            int(time.time()) - 400).encode(
            'utf-8')
        mock_s3_obj = mock.Mock()
        mock_s3_obj.Object.return_value = mock_file
        self.mock_boto.resource.return_value = mock_s3_obj

        self.plan["plan_run_uuid"] = str(uuid.uuid4())
        assert_raises(ShutdownPlanException, self.runner.check_for_cluster_done)

    def test_check_for_cluster_done_object_error(self):
        from ardere.exceptions import ShutdownPlanException

        os.environ["s3_ready_bucket"] = "test_bucket"
        mock_file = mock.Mock()
        mock_file.get.return_value = {"Body": mock_file}
        mock_file.read.return_value = "{}".format(
            int(time.time()) - 400).encode(
            'utf-8')
        mock_s3_obj = mock.Mock()
        mock_s3_obj.Object.side_effect = ClientError(
            {"Error": {}}, None
        )
        self.mock_boto.resource.return_value = mock_s3_obj

        self.plan["plan_run_uuid"] = str(uuid.uuid4())
        assert_raises(ShutdownPlanException, self.runner.check_for_cluster_done)

    def test_cleanup_cluster(self):
        self.plan["plan_run_uuid"] = str(uuid.uuid4())

        self.runner.cleanup_cluster()
        self.mock_boto.resource.assert_called()

    def test_cleanup_cluster_error(self):
        self.plan["plan_run_uuid"] = str(uuid.uuid4())

        mock_s3 = mock.Mock()
        self.mock_boto.resource.return_value = mock_s3
        mock_s3.Object.side_effect = ClientError(
            {"Error": {}}, None
        )
        self.runner.cleanup_cluster()
        mock_s3.Object.assert_called()

    def test_drain_check_draining(self):
        from ardere.exceptions import UndrainedInstancesException
        self.mock_ecs.all_services_done.return_value = True
        self.runner.check_drained()
        self.mock_ecs.all_services_done.return_value = False
        assert_raises(UndrainedInstancesException,
                      self.runner.check_drained)


class TestValidation(unittest.TestCase):
    def _make_FUT(self):
        from ardere.step_functions import PlanValidator
        return PlanValidator()

    def test_validate_success(self):
        schema = self._make_FUT()
        schema.context["boto"] = mock.Mock()
        plan = json.loads(fixtures.sample_basic_test_plan)
        data, errors = schema.load(plan)
        eq_(errors, {})
        eq_(len(data["steps"]), len(plan["steps"]))

    def test_validate_fail_ecs_name(self):
        schema = self._make_FUT()
        schema.context["boto"] = mock.Mock()
        plan = json.loads(fixtures.sample_basic_test_plan)
        plan['ecs_name'] = ''
        data, errors = schema.load(plan)
        eq_(errors, {'ecs_name': ['Plan ecs_name missing']})
        plan['ecs_name'] += '*'
        data, errors = schema.load(plan)
        eq_(errors, {'ecs_name':
                         ['Plan ecs_name contained invalid characters']})
        plan['ecs_name'] = 'a' * 512
        data, errors = schema.load(plan)
        eq_(errors, {'ecs_name': ['Plan ecs_name too long']})

    def test_validate_fail_step_name(self):
        schema = self._make_FUT()
        schema.context["boto"] = mock.Mock()
        plan = json.loads(fixtures.sample_basic_test_plan)
        plan['steps'][0]['name'] = ''
        data, errors = schema.load(plan)
        eq_(errors, {'steps': {0: {'name': ['Step name missing']}}})
        plan['steps'][0]['name'] = '*'
        data, errors = schema.load(plan)
        eq_(errors,
            {'steps': {0: {'name': ['Step name contains invalid characters']}}}
            )
        plan['steps'][0]['name'] = 'a' * 512
        data, errors = schema.load(plan)
        eq_(errors, {'steps': {0: {'name': ['Step name too long']}}})

    def test_validate_fail(self):
        schema = self._make_FUT()
        schema.context["boto"] = mock_boto = mock.Mock()
        mock_client = mock.Mock()
        mock_boto.client.return_value = mock_client
        mock_client.describe_clusters.return_value = {"clusters": []}
        plan = json.loads(fixtures.sample_basic_test_plan)
        data, errors = schema.load(plan)
        eq_(len(data["steps"]), len(plan["steps"]))
        eq_(len(errors), 1)
