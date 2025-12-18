# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Protocol


class AsgSchedulingEnvironment(Protocol):
    schedule_tag_key: str
    asg_scheduled_rule_prefix: str

    # deprecated property (used for migration only)
    asg_metadata_tag_key: str
