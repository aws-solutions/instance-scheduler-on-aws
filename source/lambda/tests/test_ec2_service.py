from unittest import mock
import os
from configuration.instance_schedule import InstanceSchedule
import configuration

mock.patch.dict(os.environ, {configuration.ENV_SCHEDULE_FREQUENCY: '10'}).start()
mock.patch.dict(os.environ, {'MAINTENANCE_WINDOW_TABLE': 'test_table'}).start()

from schedulers import Ec2Service
from util.named_tuple_builder import as_namedtuple
from schedulers.instance_scheduler import InstanceScheduler
import datetime
from freezegun import freeze_time
from mock import patch


def test_ssm_maintenance_windows_1(mocker):
    window_list = [{
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Enabled': True,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-04-09T19:00Z'
    }]
    ec2_service = Ec2Service()
    mocker.patch.object(ec2_service, 'get_ssm_windows')
    ec2_service.get_ssm_windows.return_value = window_list
    mocker.patch.object(ec2_service, '_logger')
    response = ec2_service.ssm_maintenance_windows

    assert response['mon-1'].periods[0]['period'].name == 'mon-1-period'
    assert response['mon-1'].periods[0]['period'].begintime == datetime.time(18, 50)
    assert response['mon-1'].periods[0]['period'].endtime == datetime.time(20, 0)
    assert response['mon-1'].periods[0]['period'].months == {4}
    assert response['mon-1'].periods[0]['period'].monthdays == {9}


def test_ssm_maintenance_windows_2(mocker):
    window_list = [{
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Enabled': True,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-05-10T15:00Z'
    }]
    ec2_service = Ec2Service()
    mocker.patch.object(ec2_service, 'get_ssm_windows')
    ec2_service.get_ssm_windows.return_value = window_list
    mocker.patch.object(ec2_service, '_logger')
    response = ec2_service.ssm_maintenance_windows

    assert response['mon-1'].periods[0]['period'].name == 'mon-1-period'
    assert response['mon-1'].periods[0]['period'].begintime == datetime.time(14, 50)
    assert response['mon-1'].periods[0]['period'].endtime == datetime.time(16, 0)
    assert response['mon-1'].periods[0]['period'].months == {5}
    assert response['mon-1'].periods[0]['period'].monthdays == {10}


@freeze_time("2020-05-10 15:30:34")
def test_check_window_running_1(mocker):
    window = {
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Enabled': True,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-05-10T15:00Z'
    }
    ec2_service = Ec2Service()
    assert ec2_service.check_window_running(window)


@freeze_time("2020-05-11 15:30:34")
def test_check_window_running_2(mocker):
    window = {
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Enabled': True,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-05-10T15:00Z'
    }
    ec2_service = Ec2Service()
    assert not ec2_service.check_window_running(window)


def test_get_ssm_windows(mocker):
    window_list = [{
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Duration': 1,
        'NextExecutionTime': '2020-04-09T19:00Z'
    }]
    ec2_service = Ec2Service()
    mocker.patch.object(ec2_service, 'get_ssm_windows_service')
    mocker.patch.object(ec2_service, 'get_ssm_windows_db')
    mocker.patch.object(ec2_service, 'process_ssm_window')
    mocker.patch.object(ec2_service, 'remove_unused_windows')
    ec2_service.get_ssm_windows_db.return_value = window_list
    response = ec2_service.get_ssm_windows()
    assert response == window_list


def test_process_ssm_window_1(mocker):
    ssm_windows_db = [
    {
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Duration': 1,
        'NextExecutionTime': '2020-04-09T19:00Z'
    },
    {
        'WindowId': 'mw-018e7137c74304wb5',
        'Name': 'mon-2',
        'Duration': 1,
        'NextExecutionTime': '2020-04-10T19:00Z'
    }
    ]
    window = {
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Duration': 1,
        'NextExecutionTime': '2020-04-09T19:00Z'
    }
    ec2_service = Ec2Service()
    mocker.patch.object(ec2_service, 'put_window_dynamodb')
    response = ec2_service.process_ssm_window(window, ssm_windows_db)
    ec2_service.put_window_dynamodb.assert_called_with(window)


def test_process_ssm_window_2(mocker):
    ssm_windows_db = [
    {
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-1',
        'Enabled': True,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-04-09T19:00Z'
    },
    {
        'WindowId': 'mw-018e7137c74304wb5',
        'Name': 'mon-2',
        'Enabled': False,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-04-10T19:00Z'
    }
    ]
    window = {
        'WindowId': 'mw-018e7137c74304cb5',
        'Name': 'mon-3',
        'Enabled': True,
        'Duration': 1,
        'Cutoff': 0,
        'Schedule': 'cron(0 10 19 ? * * *)',
        'NextExecutionTime': '2020-04-09T19:00Z'
    }
    ec2_service = Ec2Service()
    mocker.patch.object(ec2_service, 'put_window_dynamodb')
    response = ec2_service.process_ssm_window(window, ssm_windows_db)
    ec2_service.put_window_dynamodb.assert_called_with(window)