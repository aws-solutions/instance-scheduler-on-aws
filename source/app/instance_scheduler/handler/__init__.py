# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Sequence as _Sequence
from typing import Any as _Any
from typing import Final as _Final

from instance_scheduler.handler.base import Handler
from instance_scheduler.handler.cfn_schedule import CfnScheduleHandler
from instance_scheduler.handler.cli import CliHandler
from instance_scheduler.handler.config_resource import SchedulerSetupHandler
from instance_scheduler.handler.scheduling_orchestrator import (
    SchedulingOrchestratorHandler,
)
from instance_scheduler.handler.scheduling_request import SchedulingRequestHandler
from instance_scheduler.handler.spoke_registration import SpokeRegistrationHandler

handlers: _Final[_Sequence[type[Handler[_Any]]]] = (
    SchedulingRequestHandler,
    SchedulerSetupHandler,
    CfnScheduleHandler,
    CliHandler,
    SchedulingOrchestratorHandler,
    SpokeRegistrationHandler,
)
