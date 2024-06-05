# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from instance_scheduler.configuration.running_period import RunningPeriod
from instance_scheduler.configuration.running_period_dict_element import (
    RunningPeriodDictElement,
)
from instance_scheduler.handler.scheduling_request import (
    SchedulingRequest,
    SchedulingRequestHandler,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.store.ddb_config_item_store import DdbConfigItemStore
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.schedulers.states import InstanceState
from tests.context import MockLambdaContext
from tests.integration.helpers.ec2_helpers import (
    create_ec2_instances,
    get_current_state,
    stop_ec2_instances,
)
from tests.integration.helpers.run_handler import multi_period_schedule, simple_schedule
from tests.logger import MockLogger
from tests.test_utils.mock_scheduling_request_environment import (
    MockSchedulingRequestEnvironment,
)

stop_after_noon_period: RunningPeriodDictElement = {
    "period": RunningPeriod(
        name="test-period",
        begintime=time(0, 0, 0),
        endtime=time(12, 0, 0),
    )
}


def test_passing_tz_unaware_dt_to_scheduling_request_handler_throws_error(
    config_item_store: DdbConfigItemStore,
) -> None:
    # testing if raised by handler, not just scheduling_context constructor
    event: SchedulingRequest = {
        "action": "scheduler:run",
        "account": "123456789012",
        "region": "us-east-1",
        "service": "ec2",
        "current_dt": datetime(2023, 6, 19, 12, 0, 0).isoformat(),
        "dispatch_time": "2023-05-12 14:55:10.600619",
    }

    with pytest.raises(ValueError):
        handler = SchedulingRequestHandler(
            event, MockLambdaContext(), MockSchedulingRequestEnvironment(), MockLogger()
        )
        handler.handle_request()


@freeze_time(datetime(2023, 8, 13, 0, 0, 0, tzinfo=ZoneInfo("Australia/Sydney")))
def test_weekday_boundaries_respect_schedule_timezone(
    ec2_instance_states: InstanceStates,
) -> None:
    """
    This is a real-world scenario that used to fail in 1.3.0:
    The instance would not be started on sunday morning Australia time because the weekdays
    expression was being compared using UTC meaning that the sunday check failed at 0:00 sunday morning because
    UTC was still in Saturday
    """
    with multi_period_schedule(
        name="test-schedule",
        timezone="Australia/Sydney",
        period_definitions=[
            PeriodDefinition(
                name="weekdays",
                begintime="07:00",
                endtime="21:00",
                weekdays={"mon-fri"},
            ),
            PeriodDefinition(
                name="sun2", begintime="00:00", endtime="11:00", weekdays={"sun#2"}
            ),
            PeriodDefinition(
                name="sun3", begintime="00:00", endtime="11:00", weekdays={"sun#3"}
            ),
        ],
    ) as context:
        (instance,) = create_ec2_instances(1, schedule_name="test-schedule")
        # instance is stopped and last desired state is stopped
        stop_ec2_instances(instance)
        ec2_instance_states.set_instance_state(instance, InstanceState.STOPPED)
        ec2_instance_states.save()

        aus_time = datetime(2023, 8, 13, 0, 0, 0, tzinfo=ZoneInfo("Australia/Sydney"))
        context.run_scheduling_request_handler(dt=aus_time)

        assert get_current_state(instance) == "running"


@pytest.mark.parametrize(
    "tz,expected",
    [
        # all instances between 0-12 should be running, all instances between 12-24 should be stopped
        ("Etc/GMT+12", "running"),  # local time: 00:00
        ("Etc/GMT+10", "running"),  # local time: 02:00
        ("Etc/GMT+5", "running"),  # local time: 07:00
        ("Etc/GMT", "stopped"),  # local time: 12:00
        ("Etc/GMT-5", "stopped"),  # local time: 17:00
        ("Etc/GMT-10", "stopped"),  # local time: 22:00
        ("Etc/GMT-13", "running"),  # local time: 01:00
    ],
)
def test_time_zones(
    ec2_instance: str,
    ec2_instance_states: InstanceStates,
    tz: str,
    expected: str,
) -> None:
    ec2_instance_states.set_instance_state(ec2_instance, InstanceState.RUNNING)
    ec2_instance_states.save()

    with simple_schedule(begintime="0:00", endtime="12:00", timezone=tz) as context:
        # run at 12:00 utc (should be translated to schedule time)
        context.run_scheduling_request_handler(
            dt=datetime(2023, 6, 9, 12, 0, 0, tzinfo=timezone.utc)
        )
        assert get_current_state(ec2_instance) == expected
