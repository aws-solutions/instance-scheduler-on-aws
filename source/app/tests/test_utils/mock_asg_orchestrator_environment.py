# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field

from instance_scheduler.handler.environments.asg_orch_env import AsgOrchEnv


@dataclass(frozen=True)
class MockAsgOrchestratorEnvironment(AsgOrchEnv):
    user_agent_extra: str = "my-user-agent-extra"

    issues_topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    logger_raise_exceptions: bool = False

    config_table_name: str = "my-config-table-name"
    enable_schedule_hub_account: bool = True
    schedule_regions: list[str] = field(default_factory=list)
    asg_scheduler_name: str = "asg-scheduling-request-handler-lambda"
