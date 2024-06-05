# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

import boto3
from aws_lambda_powertools import Logger as PowerToolsLogger

from instance_scheduler.configuration.ssm import replace_ssm_references_with_account_ids
from instance_scheduler.handler.environments.asg_orch_env import AsgOrchEnv
from instance_scheduler.handler.environments.orchestrator_environment import (
    OrchestratorEnvironment,
)
from instance_scheduler.model.ddb_config_item import DdbConfigItem
from instance_scheduler.util.logger import Logger

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
else:
    LambdaContext = object


@dataclass(frozen=True)
class SchedulingTarget:
    account: str
    service: str
    region: str

    def __str__(self) -> str:
        return f"{self.account}-{self.region}-{self.service}"


def get_account_ids(
    ddb_config_item: DdbConfigItem,
    env: Union[OrchestratorEnvironment, AsgOrchEnv],
    logger: Union[Logger, PowerToolsLogger],
    context: LambdaContext,
) -> Iterator[str]:
    """
    Iterates account and cross-account-roles of the accounts to operate on
    :return:
    """
    processed_accounts = []
    hub_account_id = context.invoked_function_arn.split(":")[4]

    if env.enable_schedule_hub_account:
        processed_accounts.append(hub_account_id)
        yield hub_account_id

    for remote_account in replace_ssm_references_with_account_ids(
        ddb_config_item.remote_account_ids
    ):
        if not remote_account:
            continue

        if remote_account in processed_accounts:
            logger.warning("Remote account {} is already processed", remote_account)
            continue

        yield remote_account


def list_all_targets(
    ddb_config_item: DdbConfigItem,
    env: OrchestratorEnvironment,
    logger: Union[Logger, PowerToolsLogger],
    context: LambdaContext,
) -> Iterator[SchedulingTarget]:
    """
    Iterates account and cross-account-roles of the accounts to operate on
    :return:
    """
    services = env.scheduled_services()
    regions = (
        env.schedule_regions if env.schedule_regions else [boto3.Session().region_name]
    )

    for service in services:
        for region in regions:
            for account in get_account_ids(ddb_config_item, env, logger, context):
                yield SchedulingTarget(account=account, service=service, region=region)
