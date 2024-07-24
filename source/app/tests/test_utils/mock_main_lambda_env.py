# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass

from instance_scheduler.handler.environments.main_lambda_environment import (
    MainLambdaEnv,
)


@dataclass(frozen=True)
class MockMainLambdaEnv(MainLambdaEnv):
    log_group: str = "my-log-group"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    solution_version: str = "v9.9.9"
    enable_debug_logging: bool = True
    user_agent_extra: str = "my-user-agent-extra"
    enable_aws_organizations: bool = False
    config_table_name: str = "my-config-table-name"
