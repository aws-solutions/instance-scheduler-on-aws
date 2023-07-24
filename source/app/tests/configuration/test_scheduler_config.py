# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from instance_scheduler.configuration import scheduler_config


def test_inf_scheduler_display() -> None:
    assert scheduler_config.INF_SCHEDULE_DISPLAY == (
        "Configuration:\n"
        'Scheduled services = "{}"\n'
        'Schedule clusters = "{}"\n'
        'Create RDS instance snapshot = "{}"\n'
        'Tagname = "{}"\n'
        'Default timezone = "{}"\n'
        'Trace = "{}"\n'
        'Enable SSM Maintenance Windows = "{}"\n'
        'Use metrics = "{}"\n'
        'Regions = "{}"\n'
        'Started tags = "{}"\n'
        'Stopped tags = "{}"\n'
        'Process Lambda account = "{}"\n'
        'Scheduler Role Name = "{}"\n'
        'Namespace = "{}"\n'
        'Organization Id = "{}"\n'
        'Aws Partition = "{}"\n'
        'Remote Account Ids = "{}"'
    )


def test_tag_val_str() -> None:
    assert scheduler_config.TAG_VAL_STR == "{{{}}}"
