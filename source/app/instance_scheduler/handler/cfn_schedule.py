# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, NotRequired, Optional, TypedDict, TypeGuard

from botocore.exceptions import ClientError

from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)
from instance_scheduler.model.period_definition import PeriodDefinition
from instance_scheduler.model.period_identifier import PeriodIdentifier
from instance_scheduler.model.schedule_definition import ScheduleDefinition
from instance_scheduler.model.store.dynamo_period_definition_store import (
    DynamoPeriodDefinitionStore,
)
from instance_scheduler.model.store.dynamo_schedule_definition_store import (
    DynamoScheduleDefinitionStore,
)
from instance_scheduler.util.custom_resource import (
    CustomResource,
    CustomResourceRequest,
    CustomResourceResponse,
)
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object


"""
  SampleSchedule:
    Type: 'Custom::ServiceInstanceSchedule'
    Properties:
      ServiceToken: !Ref ServiceInstanceScheduleServiceTokenARN #do not edit this line
      NoStackPrefix: 'False'
      Name: my-renamed-sample-schedule
      Description: a full sample template for creating cfn schedules showing all possible values
      Timezone: America/New_York
      Enforced: 'True'
      Hibernate: 'True'
      RetainRunning: 'True'
      StopNewInstances: 'True'
      SsmMaintenanceWindow: 'my_window_name'
      OverrideStatus: 'running'
      Periods:
      - Description: run from 9-5 on the first 3 days of March
        BeginTime: '9:00'
        EndTime: '17:00'
        InstanceType: 't2.micro'
        MonthDays: '1-3'
        Months: '3'
      - Description: run from 2pm-5pm on the weekends
        BeginTime: '14:00'
        EndTime: '17:00'
        InstanceType: 't2.micro'
        WeekDays: 'Sat-Sun'
"""


class CfnSchedulePeriodProperties(TypedDict, total=False):
    Description: NotRequired[str]
    BeginTime: NotRequired[str]
    EndTime: NotRequired[str]
    InstanceType: NotRequired[str]
    MonthDays: NotRequired[str]
    Months: NotRequired[str]
    WeekDays: NotRequired[str]


class CfnScheduleResourceProperties(TypedDict, total=False):
    ServiceToken: str
    NoStackPrefix: NotRequired[str]
    Name: NotRequired[str]
    Description: NotRequired[str]
    Timezone: NotRequired[str]
    Enforced: NotRequired[str]
    Hibernate: NotRequired[str]
    RetainRunning: NotRequired[str]
    StopNewInstances: NotRequired[str]
    SsmMaintenanceWindow: NotRequired[list[str] | str]
    UseMaintenanceWindow: NotRequired[str]
    OverrideStatus: NotRequired[str]
    Periods: NotRequired[list[CfnSchedulePeriodProperties]]


class InvalidScheduleConfiguration(Exception):
    pass


class CfnScheduleHandler(CustomResource[CfnScheduleResourceProperties]):
    """
    Implements custom resource handler for CFN support for schedules/periods
    """

    def __init__(
        self,
        event: CustomResourceRequest[CfnScheduleResourceProperties],
        context: LambdaContext,
        env: MainLambdaEnv,
    ) -> None:
        """
        Initializes instance
        :param event: CFN event
        :param context: Lambda context
        """
        CustomResource.__init__(self, event, context)
        self._logger = self._init_logger(env)
        self.schedule_store = DynamoScheduleDefinitionStore(env.config_table_name)
        self.period_store = DynamoPeriodDefinitionStore(env.config_table_name)

    def _init_logger(self, env: MainLambdaEnv) -> Logger:
        classname = self.__class__.__name__
        dt = datetime.now(timezone.utc)
        log_stream = "{}-{:0>4d}{:0>2d}{:0>2d}".format(
            classname, dt.year, dt.month, dt.day
        )
        return Logger(
            log_group=env.log_group,
            log_stream=log_stream,
            topic_arn=env.topic_arn,
            debug=env.enable_debug_logging,
        )

    @staticmethod
    def is_handling_request(
        event: Mapping[str, Any]
    ) -> TypeGuard[CustomResourceRequest[CfnScheduleResourceProperties]]:
        """
        Tests if this handler handles the event
        :param event: Tested event
        :return: True if this is custom resource event for configuring schedule/periods
        """
        return (
            event.get("StackId") is not None
            and event.get("ResourceType") == "Custom::ServiceInstanceSchedule"
        )

    def _create_request(self) -> CustomResourceResponse:
        """
        create a new CloudFormation-Managed schedule

        This request will fail if creating a new schedule would overwrite an existing one
        """
        self._logger.info(f"received create request for:\n{self.resource_properties}")
        try:
            schedule_def, period_defs = self._parse_schedule_template_item(
                self.resource_properties
            )
            # ----- Begin Transaction -------
            with self.schedule_store.new_transaction() as transaction:
                transaction.add(
                    self.schedule_store.transact_put(schedule_def, overwrite=False)
                )
                for period_def in period_defs:
                    transaction.add(
                        self.period_store.transact_put(period_def, overwrite=False)
                    )
            # ------ End Transaction --------
            self._logger.info(
                f"successfully created schedule:"
                f"\n{schedule_def}"
                f"\n{[str(period_def) for period_def in period_defs]}"
            )
            return self.OkResponse(physical_resource_id=schedule_def.name)
        except ClientError as ce:
            # indicates a transaction failure
            return self.ErrorResponse(reason=f"unable to create schedule: {ce}")
        finally:
            self._logger.flush()

    def _update_request(self) -> CustomResourceResponse:
        """
        CloudFormation update request against a schedule managed by a CFN stack

        There are 2 possible scenarios that we need to handle

        Schedule name not changed by update -- schedule should be updated in place

            To handle this, we perform a write transaction with overwrite=true to update the schedule in dynamodb
            without needing any additional deletions


        Schedule name changes due to update -- old schedule must be deleted AND we must be careful not to conflict
        with other already existing schedules

            To handle not conflicting with existing schedules, we set overwrite=false such that if changing the
            schedule name would overwrite an existing schedule we will instead error on the write transaction

            To handle correctly deleting the old schedule, we return the new schedule name as the
            physical_resource_id of this resource. When this returned physical_resource_id changes (which it will
            because the schedule name has changed from the last change request), CloudFormation will issue a
            delete_request against the original resource which will handle the deletion behavior for us.
        """

        self._logger.info(f"received update request for:\n{self.resource_properties}")
        try:
            schedule_def, period_defs = self._parse_schedule_template_item(
                self.resource_properties
            )

            old_sched_def, _ = self._parse_schedule_template_item(
                self.old_resource_properties
            )
            # ----- Begin Transaction -------
            with self.schedule_store.new_transaction() as transaction:
                if schedule_def.name == old_sched_def.name:
                    # we are updating the same schedule, so we need to overwrite
                    transaction.add(
                        self.schedule_store.transact_put(schedule_def, overwrite=True)
                    )
                else:
                    # the schedule name is changing, fail if a schedule already exists with the same name
                    transaction.add(
                        self.schedule_store.transact_put(schedule_def, overwrite=False)
                    )

                for period_def in period_defs:
                    transaction.add(
                        self.period_store.transact_put(period_def, overwrite=True)
                    )
            # ------ End Transaction --------
            self._logger.info(
                f"successfully updated schedule:"
                f"\n{schedule_def}"
                f"\n{[str(period_def) for period_def in period_defs]}"
            )
            return self.OkResponse(physical_resource_id=schedule_def.name)
        except ClientError as ce:
            # indicates a transaction failure
            return self.ErrorResponse(reason=f"unable to update schedule: {ce}")
        finally:
            self._logger.flush()

            # handles Delete request from CloudFormation

    def _delete_request(self) -> CustomResourceResponse:
        """
        delete a cloudformation managed schedule

        This request will indicate potential problems by failing if the schedule or any of its periods do not exist
        """
        self._logger.info(f"received delete request for:\n{self.resource_properties}")
        try:
            schedule_def, period_defs = self._parse_schedule_template_item(
                self.resource_properties
            )
            # ----- Begin Transaction -------
            with self.schedule_store.new_transaction() as transaction:
                transaction.add(
                    self.schedule_store.transact_delete(
                        schedule_def.name, error_if_missing=False
                    )
                )
                for period_def in period_defs:
                    transaction.add(
                        self.period_store.transact_delete(
                            period_def.name, error_if_missing=False
                        )
                    )
            # ------ End Transaction --------
            self._logger.info(
                f"successfully deleted schedule {schedule_def.name} and periods {[p_def.name for p_def in period_defs]}"
            )
            return self.OkResponse(physical_resource_id=schedule_def.name)
        except ClientError as ce:
            # indicates a transaction failure
            return self.ErrorResponse(reason=f"unable to delete schedule: {ce}")
        finally:
            self._logger.flush()

    def _parse_schedule_template_item(
        self, resource_properties: CfnScheduleResourceProperties
    ) -> tuple[ScheduleDefinition, list[PeriodDefinition]]:
        # ---------------- Validation ----------------#
        self._validate_schedule_props_structure(resource_properties)
        for period_props in resource_properties.get("Periods", []):
            _validate_period_props_structure(period_props)

        # ------------ PARSE SCHEDULE NAME ------------#
        schedule_name: str = resource_properties.get("Name", self.logical_resource_id)
        if resource_properties.get("NoStackPrefix", "False").lower() == "false":
            schedule_name = f"{self.stack_name}-{schedule_name}"

        # --------------- PARSE PERIODS ---------------#
        period_defs = []
        period_identifiers = []
        period_counter = 0
        for period_props in resource_properties.get("Periods", []):
            period_counter += 1
            try:
                period_name = "{}-period-{:0>4d}".format(schedule_name, period_counter)
                period_def = PeriodDefinition(
                    name=period_name,
                    description=period_props.get(
                        "Description",
                        f"Schedule {schedule_name} period {period_counter}, "
                        f"do not delete or update manually",
                    ),
                    begintime=period_props.get("BeginTime", None),
                    endtime=period_props.get("EndTime", None),
                    weekdays=_ensure_set(period_props.get("WeekDays", None)),
                    months=_ensure_set(period_props.get("Months", None)),
                    monthdays=_ensure_set(period_props.get("MonthDays", None)),
                    configured_in_stack=self.stack_id,
                )

                period_defs.append(period_def)
                period_identifiers.append(
                    PeriodIdentifier.of(
                        period_name, period_props.get("InstanceType", None)
                    )
                )
            except Exception as ex:
                raise InvalidScheduleConfiguration(
                    f"Error parsing period {period_counter} for schedule {schedule_name}: {ex}"
                )

        # --------------- PARSE SCHEDULE ---------------#
        try:
            sche_def = ScheduleDefinition(
                name=schedule_name,
                periods=period_identifiers,
                timezone=resource_properties.get("Timezone", None),
                description=resource_properties.get("Description", None),
                override_status=resource_properties.get("OverrideStatus", None),
                stop_new_instances=_parse_bool(
                    resource_properties.get("StopNewInstances", None)
                ),
                ssm_maintenance_window=_ensure_list(
                    resource_properties.get("SsmMaintenanceWindow")
                ),
                use_maintenance_window=_parse_bool(
                    resource_properties.get("UseMaintenanceWindow", None)
                ),
                enforced=_parse_bool(resource_properties.get("Enforced", None)),
                hibernate=_parse_bool(resource_properties.get("Hibernate", None)),
                retain_running=_parse_bool(
                    resource_properties.get("RetainRunning", None)
                ),
                configured_in_stack=self.stack_id,
            )
        except Exception as ex:
            raise InvalidScheduleConfiguration(
                f"Error parsing schedule {schedule_name}: {ex}"
            )

        return sche_def, period_defs

    def _validate_schedule_props_structure(
        self, props: CfnScheduleResourceProperties
    ) -> None:
        for key in props.keys():
            if key in {"ServiceToken", "Timeout"}:
                # these properties used to be part of the sample template in the IG, but have been removed in July 2023,
                # They do not do anything, but customers may still have old templates that include them,
                # so we need to not break compatibility
                continue

            if key in {"Metrics"}:
                # deprecated keys that no longer do anything but that not should throw errors
                self._logger.warning(
                    f'Schedule contains deprecated field "${key}", this field will be ignored.'
                )
                continue

            if key not in CfnScheduleResourceProperties.__annotations__.keys():
                raise InvalidScheduleConfiguration(
                    f"Unknown schedule property {key}, valid properties are "
                    f"{CfnScheduleResourceProperties.__annotations__.keys()}"
                )


def _parse_bool(bool_str: Optional[str]) -> Optional[bool]:
    if bool_str is None:
        return None
    if bool_str.lower() == "true":
        return True
    elif bool_str.lower() == "false":
        return False
    else:
        raise ValueError(f"unknown bool value {bool_str}, must be 'true' or 'false'")


def _ensure_set(s: list[str] | set[str] | str | None) -> set[str] | None:
    if s is None:
        return None
    if isinstance(s, list):
        return set(s)
    if isinstance(s, str):
        return set(s.split(","))
    return s


def _ensure_list(s: list[str] | set[str] | str | None) -> list[str] | None:
    if s is None:
        return None
    if isinstance(s, set):
        return list(s)
    if isinstance(s, str):
        return list(s.split(","))
    return s


def _validate_period_props_structure(props: CfnSchedulePeriodProperties) -> None:
    for key in props.keys():
        if key not in CfnSchedulePeriodProperties.__annotations__.keys():
            raise InvalidScheduleConfiguration(
                f"Unknown period property {key}, valid properties are "
                f"{CfnSchedulePeriodProperties.__annotations__.keys()}"
            )
