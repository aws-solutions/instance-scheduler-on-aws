# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from os import environ
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
)

from aws_lambda_powertools.utilities.parameters import SSMProvider
from instance_scheduler.configuration.scheduling_context import SchedulingEnvironment
from instance_scheduler.handler.region_registration_events_handler import (
    RegionRegistrationState,
)
from instance_scheduler.model.store.dynamo_resource_registry import (
    DynamoResourceRegistry,
)
from instance_scheduler.observability.powertools_logging import (
    LogContext,
    powertools_logger,
    should_log_events,
)
from instance_scheduler.scheduling.asg.asg_service import AsgService
from instance_scheduler.scheduling.ec2 import Ec2Service
from instance_scheduler.scheduling.rds import RdsService
from instance_scheduler.scheduling.resource_registration import (
    deregister_asg_resources,
    deregister_ec2_resources,
    deregister_rds_resources,
    register_asg_resources,
    register_ec2_resources,
    register_rds_resources,
)
from instance_scheduler.util import safe_json
from instance_scheduler.util.app_env_utils import AppEnvError
from instance_scheduler.util.session_manager import (
    assume_role,
    lambda_execution_role,
)
from pydantic import BaseModel

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from mypy_boto3_ssm.client import SSMClient
else:
    SSMClient = object
    LambdaContext = object


class SpokeRegistrationRequest(BaseModel):
    account: str
    region: str
    operation: Literal["Register", "Deregister"]


@dataclass(frozen=True)
class SpokeRegistrationEnvironment(SchedulingEnvironment):
    user_agent_extra: str
    config_table: str
    registry_table: str
    scheduler_role_name: str
    schedule_tag_key: str
    hub_stack_name: str
    scheduling_interval_minutes: int
    asg_scheduled_rule_prefix: str
    asg_metadata_tag_key: str
    local_event_bus_name: str
    global_event_bus_name: str
    ssm_param_path_name: str
    ssm_param_update_role_name: str

    @staticmethod
    def from_env() -> "SpokeRegistrationEnvironment":
        try:
            return SpokeRegistrationEnvironment(
                user_agent_extra=environ["USER_AGENT_EXTRA"],
                config_table=environ["CONFIG_TABLE"],
                registry_table=environ["REGISTRY_TABLE"],
                scheduler_role_name=environ["SCHEDULER_ROLE_NAME"],
                schedule_tag_key=environ["SCHEDULE_TAG_KEY"],
                hub_stack_name=environ["HUB_STACK_NAME"],
                scheduling_interval_minutes=int(environ["SCHEDULING_INTERVAL_MINUTES"]),
                asg_scheduled_rule_prefix=environ["ASG_SCHEDULED_RULES_PREFIX"],
                asg_metadata_tag_key=environ["ASG_METADATA_TAG_KEY"],
                local_event_bus_name=environ["LOCAL_EVENT_BUS_NAME"],
                global_event_bus_name=environ["GLOBAL_EVENT_BUS_NAME"],
                ssm_param_path_name=environ["SSM_PARAM_PATH_NAME"],
                ssm_param_update_role_name=environ["SSM_PARAM_UPDATE_ROLE_NAME"],
            )
        except KeyError as err:
            raise AppEnvError(
                f"Missing required application environment variable: {err.args[0]}"
            ) from err


class SpokeRegistrationException(Exception):
    pass


class InvalidRequestException(Exception):
    pass


logger: Final = powertools_logger()


@logger.inject_lambda_context(log_event=should_log_events(logger), clear_state=True)
def lambda_handler(
    event: Mapping[str, Any],
    context: LambdaContext,
) -> dict[str, Any]:
    env: Final = SpokeRegistrationEnvironment.from_env()
    registry = DynamoResourceRegistry(env.registry_table)
    registration_request = SpokeRegistrationRequest.model_validate(event)

    logger.append_keys(
        context=LogContext.REGISTRATION.value,
        account=registration_request.account,
        region=registration_request.region,
    )

    def set_registration_status(
        env: SpokeRegistrationEnvironment,
        registration_request: SpokeRegistrationRequest,
        status: RegionRegistrationState,
    ) -> None:
        if registration_request.account == lambda_execution_role().account:
            assumed_role = lambda_execution_role()
        else:
            assumed_role = assume_role(
                account=registration_request.account,
                region=environ["AWS_REGION"],
                role_name=env.ssm_param_update_role_name,
            )

        ssm_client: SSMClient = assumed_role.client("ssm")
        ssm_provider = SSMProvider(boto3_client=ssm_client)
        ssm_provider.set(
            name=f"{env.ssm_param_path_name}/{registration_request.region}",
            value=status.value,
            overwrite=True,
            tier="Advanced",
            parameter_type="String",
        )
        return None

    try:
        match registration_request.operation:
            case "Register":
                logger.info(
                    f"Received registration request for {registration_request.account}-{registration_request.region}"
                )
                set_registration_status(
                    env, registration_request, RegionRegistrationState.REGISTERING
                )
                scheduler_role = assume_role(
                    account=registration_request.account,
                    region=registration_request.region,
                    role_name=env.scheduler_role_name,
                )

                register_ec2_resources(
                    Ec2Service.describe_tagged_instances(
                        scheduler_role, env.schedule_tag_key
                    ),
                    scheduler_role,
                    env,
                )
                register_rds_resources(
                    RdsService.describe_tagged_rds_resources(
                        scheduler_role, env.schedule_tag_key
                    ),
                    scheduler_role,
                    env,
                )
                register_asg_resources(
                    AsgService.describe_tagged_asgs(
                        scheduler_role, env.schedule_tag_key
                    ),
                    scheduler_role,
                    env,
                )

                set_registration_status(
                    env, registration_request, RegionRegistrationState.MANAGED
                )
            case "Deregister":
                logger.info(
                    f"Received deregistration request for {registration_request.account}-{registration_request.region}"
                )
                scheduler_role = assume_role(
                    account=registration_request.account,
                    region=registration_request.region,
                    role_name=env.scheduler_role_name,
                )

                deregister_ec2_resources(
                    registry.find_by_scheduling_target(
                        scheduler_role.account, scheduler_role.region, "ec2"
                    ),
                    scheduler_role,
                    env,
                )
                deregister_rds_resources(
                    registry.find_by_scheduling_target(
                        scheduler_role.account, scheduler_role.region, "rds"
                    ),
                    scheduler_role,
                    env,
                )
                deregister_asg_resources(
                    registry.find_by_scheduling_target(
                        scheduler_role.account, scheduler_role.region, "autoscaling"
                    ),
                    scheduler_role,
                    env,
                )
                set_registration_status(
                    env, registration_request, RegionRegistrationState.DELETED
                )
                # todo: deregistration event
            case _:
                raise InvalidRequestException(
                    f"Spoke Registration handler received an unknown request: {registration_request.operation}"
                )

        return {"statusCode": 200, "body": "success"}

        # todo: return success/fail
    except Exception as e:
        # log error to SNS, then let the lambda execution fail
        logger.error(
            f"Error handling spoke registration request {safe_json(event)}: ({e})\n{traceback.format_exc()}",
        )
        raise e
