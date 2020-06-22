from unittest import mock
import os
from configuration.instance_schedule import InstanceSchedule

mock.patch.dict(os.environ, {'MAINTENANCE_WINDOW_TABLE': 'test_table'}).start()
from schedulers import Ec2Service
from util.named_tuple_builder import as_namedtuple
from schedulers.instance_scheduler import InstanceScheduler


def test_get_desired_state_and_type_1(mocker):
    instance = {}
    schedule = InstanceSchedule(
        name='test-1',
        periods={},
        timezone='UTC',
        override_status=None,
        description=None,
        use_metrics=None,
        stop_new_instances=None,
        schedule_dt=None,
        use_maintenance_window=False,
        ssm_maintenance_window=True,
        enforced=False,
        hibernate=False,
        retain_running=False
    )
    instance['maintenance_window'] = schedule
    instance["account"] = 'test'
    instance["region"] = 'us-east-1'
    instance["service"] = 'ec2'
    instance["id"] = 'ut12y21232u'
    inst = as_namedtuple('ec2' + "Instance", instance, excludes=["tags"])
    ec2_service = Ec2Service()
    scheduler_configuration = {}
    scheduler = InstanceScheduler(ec2_service, scheduler_configuration)
    mocker.patch.object(scheduler, '_logger')
    inst_state, inst_type = scheduler.get_desired_state_and_type(schedule, inst)
    assert inst_state == 'stopped'


def test_get_desired_state_and_type_2(mocker):
    instance = {}
    schedule = InstanceSchedule(
        name='test-1',
        periods={},
        timezone='UTC',
        override_status=None,
        description=None,
        use_metrics=None,
        stop_new_instances=None,
        schedule_dt=None,
        use_maintenance_window=True,
        ssm_maintenance_window=True,
        enforced=False,
        hibernate=False,
        retain_running=False
    )
    instance['maintenance_window'] = None
    instance["account"] = 'test'
    instance["region"] = 'us-east-1'
    instance["service"] = 'ec2'
    instance["id"] = 'ut12y21232u'
    inst = as_namedtuple('ec2' + "Instance", instance, excludes=["tags"])
    ec2_service = Ec2Service()
    scheduler_configuration = {}
    scheduler = InstanceScheduler(ec2_service, scheduler_configuration)
    mocker.patch.object(scheduler, '_logger')
    inst_state, inst_type = scheduler.get_desired_state_and_type(schedule, inst)
    assert inst_state == 'stopped'