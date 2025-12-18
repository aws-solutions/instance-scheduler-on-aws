# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import datetime
from typing import Protocol

from instance_scheduler.model.store.cached_period_definition_store import (
    CachedPeriodDefinitionStore,
)
from instance_scheduler.model.store.cached_resource_registry import (
    CachedResourceRegistry,
)
from instance_scheduler.model.store.cached_schedule_definition_store import (
    CachedScheduleDefinitionStore,
)
from instance_scheduler.observability.events.events_environment import EventsEnv
from instance_scheduler.scheduling.asg.asg_scheduling_envionment import (
    AsgSchedulingEnvironment,
)
from instance_scheduler.util.session_manager import AssumedRole
from instance_scheduler.util.time import is_aware


class SchedulingEnvironment(EventsEnv, AsgSchedulingEnvironment, Protocol):
    config_table: str
    registry_table: str
    hub_stack_name: str
    schedule_tag_key: str
    scheduling_interval_minutes: int
    asg_scheduled_rule_prefix: str
    asg_metadata_tag_key: str
    local_event_bus_name: str
    global_event_bus_name: str


class SchedulingContext:
    assumed_role: AssumedRole
    current_dt: datetime.datetime
    registry: CachedResourceRegistry
    schedule_store: CachedScheduleDefinitionStore
    period_store: CachedPeriodDefinitionStore
    schedule_tag_key: str
    hub_stack_name: str
    asg_scheduled_rule_prefix: str
    scheduling_interval_minutes: int
    local_event_bus_name: str
    global_event_bus_name: str

    def __init__(
        self,
        assumed_role: AssumedRole,
        current_dt: datetime.datetime,
        env: SchedulingEnvironment,
    ):
        if not is_aware(current_dt):
            raise ValueError(
                f"SchedulingContext datetime must be timezone-Aware. Received: {current_dt}"
            )

        self.assumed_role = assumed_role
        self.current_dt = current_dt
        self.registry = CachedResourceRegistry(env.registry_table)
        self.schedule_store = CachedScheduleDefinitionStore(env.config_table)
        self.period_store = CachedPeriodDefinitionStore(env.config_table)
        self.schedule_tag_key = env.schedule_tag_key
        self.hub_stack_name = env.hub_stack_name
        self.asg_scheduled_rule_prefix = env.asg_scheduled_rule_prefix
        self.scheduling_interval_minutes = env.scheduling_interval_minutes
        self.local_event_bus_name = env.local_event_bus_name
        self.global_event_bus_name = env.global_event_bus_name
