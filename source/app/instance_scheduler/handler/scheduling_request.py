# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import copy
import inspect
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    NotRequired,
    Optional,
    TypedDict,
    TypeGuard,
    cast,
)

import boto3

from instance_scheduler import configuration
from instance_scheduler.configuration.instance_schedule import InstanceSchedule
from instance_scheduler.configuration.scheduling_context import (
    SchedulingContext,
    TagTemplate,
)
from instance_scheduler.handler.base import MainHandler
from instance_scheduler.handler.environments.scheduling_request_environment import (
    SchedulingRequestEnvironment,
)
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.model.store.in_memory_period_definition_store import (
    InMemoryPeriodDefinitionStore,
    SerializedInMemoryPeriodDefinitionStore,
)
from instance_scheduler.model.store.in_memory_schedule_definition_store import (
    InMemoryScheduleDefinitionStore,
    SerializedInMemoryScheduleDefinitionStore,
)
from instance_scheduler.model.store.period_definition_store import PeriodDefinitionStore
from instance_scheduler.model.store.schedule_definition_store import (
    ScheduleDefinitionStore,
)
from instance_scheduler.schedulers.instance_scheduler import InstanceScheduler
from instance_scheduler.schedulers.instance_states import InstanceStates
from instance_scheduler.service import Ec2Service, RdsService, Service
from instance_scheduler.util import get_boto_config, safe_json
from instance_scheduler.util.logger import Logger
from instance_scheduler.util.session_manager import assume_role, get_role_arn
from instance_scheduler.util.validation import (
    ValidationException,
    validate_string,
    validate_string_list,
)

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_lambda.client import LambdaClient
else:
    LambdaContext = object
    LambdaClient = object


class SchedulingRequest(TypedDict):
    action: Literal["scheduler:run"]
    dispatch_time: str
    account: str
    service: str
    region: str
    current_dt: str
    schedules: NotRequired[SerializedInMemoryScheduleDefinitionStore]
    periods: NotRequired[SerializedInMemoryPeriodDefinitionStore]
    schedule_names: NotRequired[list[str]]


def validate_scheduler_request(
    untyped_dict: Mapping[str, Any]
) -> TypeGuard[SchedulingRequest]:
    valid_keys = inspect.get_annotations(SchedulingRequest).keys()
    for key in untyped_dict.keys():
        if key not in valid_keys:
            raise ValidationException(
                f"{key} is not a valid parameter, valid parameters are {valid_keys}"
            )

    validate_string(untyped_dict, "dispatch_time", required=True)
    validate_string(untyped_dict, "account", required=True)
    validate_string(untyped_dict, "service", required=True)
    validate_string(untyped_dict, "region", required=True)
    validate_string(
        untyped_dict, "current_dt", required=True
    )  # todo: validate as ISO string

    if "schedules" in untyped_dict:
        InMemoryScheduleDefinitionStore.validate_serial_data(untyped_dict["schedules"])

    if "periods" in untyped_dict:
        InMemoryPeriodDefinitionStore.validate_serial_data(untyped_dict["periods"])

    if "schedule_names" in untyped_dict:
        validate_string_list(untyped_dict, "schedule_names", required=False)

    return True


def handle_scheduling_request(event: Mapping[str, Any], context: LambdaContext) -> Any:
    # todo: how to surface validation error?
    env = SchedulingRequestEnvironment.from_env()
    validate_scheduler_request(event)
    event = cast(SchedulingRequest, event)

    logger = init_logger(
        service=event["service"],
        account=event["account"],
        region=event["region"],
        env=env,
    )
    with logger:
        try:
            handler = SchedulingRequestHandler(event, context, env, logger)
            return handler.handle_request()
        except Exception as e:
            # log error to SNS, then let the lambda execution fail
            logger.error(
                "Error handling scheduling request {}: ({})\n{}",
                safe_json(event),
                e,
                traceback.format_exc(),
            )
            raise e


def init_logger(
    service: str, account: str, region: str, env: SchedulingRequestEnvironment
) -> Logger:
    log_stream_name: Final = f"Scheduler-{service}-{account}-{region}"
    dt: Final = datetime.now(timezone.utc)
    log_stream: Final = "{}-{:0>4d}{:0>2d}{:0>2d}".format(
        log_stream_name, dt.year, dt.month, dt.day
    )

    return Logger(
        log_group=env.log_group,
        log_stream=log_stream,
        topic_arn=env.topic_arn,
        debug=env.enable_debug_logging,
    )


class SchedulingRequestHandler(MainHandler[SchedulingRequest]):
    def __init__(
        self,
        event: SchedulingRequest,
        context: LambdaContext,
        env: SchedulingRequestEnvironment,
        logger: Logger,
    ) -> None:
        self._env: Final = env
        self._logger = logger
        self._function_name: Final = context.function_name
        self._hub_account_id: Final = context.invoked_function_arn.split(":")[4]
        self._event = event

    @staticmethod
    def is_handling_request(event: Mapping[str, Any]) -> TypeGuard[SchedulingRequest]:
        return str(event.get("action", "")) == "scheduler:run"

    def handle_request(self) -> Any:
        with self._logger:
            scheduling_context = build_scheduling_context(self._event, self._env)

            spoke_scheduler_role = assume_role(
                account=scheduling_context.account_id,
                region=scheduling_context.region,
                role_name=self._env.scheduler_role_name,
            )

            service_api: Service  # type:ignore[type-arg]
            match scheduling_context.service:
                case "ec2":
                    service_api = Ec2Service(
                        assumed_scheduling_role=spoke_scheduler_role,
                        logger=self._logger,
                        scheduling_context=scheduling_context,
                        env=self._env,
                    )
                case "rds":
                    service_api = RdsService(
                        assumed_scheduling_role=spoke_scheduler_role,
                        logger=self._logger,
                        scheduling_context=scheduling_context,
                        env=self._env,
                    )
                case _:
                    raise ValueError(f"Unknown service: {scheduling_context.service}")

            instance_states: Final = InstanceStates(
                self._env.state_table_name, scheduling_context.service, self._logger
            )

            scheduler: Final = InstanceScheduler(
                service_api,
                scheduling_context,
                instance_states,
                self._logger,
                self._env,
            )

            self._logger.info(
                f"Handler {self.__class__.__name__}"
                f" Running {scheduling_context.service.upper()} scheduler"
                f" for account {scheduling_context.account_id}"
                f" in region(s) {scheduling_context.region}"
                f" at {scheduling_context.current_dt}"
                f" using role {get_role_arn(account_id=scheduling_context.account_id, role_name=self._env.scheduler_role_name)}"
            )

            result: Final = {scheduling_context.account_id: scheduler.run()}

            self._logger.info("Scheduler result {}", result)

        return result

    @cached_property
    def lambda_client(self) -> LambdaClient:
        client: LambdaClient = boto3.client("lambda", config=get_boto_config())
        return client


def build_scheduling_context(
    event: SchedulingRequest, env: SchedulingRequestEnvironment
) -> SchedulingContext:
    current_dt = datetime.fromisoformat(event["current_dt"])

    return SchedulingContext(
        account_id=event["account"],
        service=event["service"],
        region=event["region"],
        current_dt=current_dt,
        default_timezone=env.default_timezone,
        schedules=load_schedules(event, env),
        scheduling_interval_minutes=env.scheduler_frequency_minutes,
        started_tags=build_tags_from_template(",".join(env.start_tags), env),
        stopped_tags=build_tags_from_template(",".join(env.stop_tags), env),
    )


def load_schedules(
    event: SchedulingRequest,
    env: SchedulingRequestEnvironment,
) -> Mapping[str, InstanceSchedule]:
    schedule_store: ScheduleDefinitionStore
    period_store: PeriodDefinitionStore

    if "schedules" in event:
        schedule_store = InMemoryScheduleDefinitionStore.deserialize(event["schedules"])
    else:
        dynamo_schedule_store = DynamoScheduleDefinitionStore(env.config_table_name)
        schedule_store = InMemoryScheduleDefinitionStore(
            dynamo_schedule_store.find_all()
        )

    if "periods" in event:
        period_store = InMemoryPeriodDefinitionStore.deserialize(event["periods"])
    else:
        dynamo_period_store = DynamoPeriodDefinitionStore(env.config_table_name)
        period_store = InMemoryPeriodDefinitionStore(dynamo_period_store.find_all())

    loaded_schedules: dict[str, InstanceSchedule] = {}
    for schedule_def in schedule_store.find_all().values():
        schedule = schedule_def.to_instance_schedule(period_store)
        loaded_schedules[schedule.name] = schedule

    return loaded_schedules


def build_tags_from_template(
    tags_str: Any,
    env: SchedulingRequestEnvironment,
    tag_variables: Optional[Any] = None,
) -> list[TagTemplate]:
    lastkey = None
    tags = {}
    for tag in tags_str.split(","):
        if "=" in tag:
            t = tag.partition("=")
            tags[t[0]] = t[2]
            lastkey = t[0]
        elif lastkey is not None:
            tags[lastkey] = ",".join([tags[lastkey], tag])

    tag_vars = {} if tag_variables is None else copy.copy(tag_variables)

    dt = datetime.now(timezone.utc)
    tag_vars.update(
        {
            configuration.TAG_VAL_SCHEDULER: env.stack_name,
            configuration.TAG_VAL_YEAR: "{:0>4d}".format(dt.year),
            configuration.TAG_VAL_MONTH: "{:0>2d}".format(dt.month),
            configuration.TAG_VAL_DAY: "{:0>2d}".format(dt.day),
            configuration.TAG_VAL_HOUR: "{:0>2d}".format(dt.hour),
            configuration.TAG_VAL_MINUTE: "{:0>2d}".format(dt.minute),
            configuration.TAG_VAL_TIMEZONE: "UTC",
        }
    )

    for tag in tags:
        value = tags[tag]
        if value not in ["", None]:
            for v in tag_vars:
                tags[tag] = tags[tag].replace("{{{}}}".format(v), tag_vars[v])

    return [{"Key": t, "Value": tags[t]} for t in tags]
