# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass

from instance_scheduler.handler.environments.orchestrator_environment import (
    OrchestratorEnvironment,
)


@dataclass(frozen=True)
class MockOrchestratorEnvironment(OrchestratorEnvironment):
    user_agent_extra: str = "my-user-agent-extra"
    topic_arn: str = "arn:aws:sns:us-east-1:123456789012:my-topic-arn"
    # references
    scheduling_request_handler_name: str = "scheduling-request-handler-lambda"
    config_table_name: str = "my-config-table-name"
    registry_table: str = "my-registry-table-name"
