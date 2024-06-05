# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from collections import Counter

from instance_scheduler.ops_monitoring.instance_counts import (
    InstanceCounts,
    InstanceCountsAggregator,
    ServiceInstanceCounts,
)


def test_merge_combines_as_expected() -> None:
    data1 = ServiceInstanceCounts(
        {
            "ec2": InstanceCountsAggregator(
                {
                    "by_type": InstanceCounts(
                        {"t2.micro": Counter({"running": 10, "stopped": 5})}
                    ),
                    "by_schedule": InstanceCounts(
                        {"schedule_a": Counter({"running": 5, "stopped": 2})}
                    ),
                },
            ),
            "rds": InstanceCountsAggregator(
                {
                    "by_type": InstanceCounts(
                        {"t3.micro": Counter({"running": 2, "stopped": 2})}
                    ),
                    "by_schedule": InstanceCounts(
                        {"schedule_b": Counter({"running": 2, "stopped": 1})}
                    ),
                },
            ),
        }
    )

    data2 = ServiceInstanceCounts(
        {
            "ec2": InstanceCountsAggregator(
                {
                    "by_type": InstanceCounts(
                        {
                            "t2.micro": Counter({"running": 5, "stopped": 3}),
                            "t2.nano": Counter({"running": 4, "stopped": 2}),
                        }
                    ),
                    "by_schedule": InstanceCounts(
                        {"schedule_a": Counter({"running": 2, "stopped": 12})}
                    ),
                },
            ),
        }
    )

    assert data1.merged_with(data2) == {
        "ec2": {
            "by_type": {
                "t2.micro": {"running": 15, "stopped": 8},
                "t2.nano": {"running": 4, "stopped": 2},
            },
            "by_schedule": {"schedule_a": {"running": 7, "stopped": 14}},
        },
        "rds": {
            "by_type": {"t3.micro": {"running": 2, "stopped": 2}},
            "by_schedule": {"schedule_b": {"running": 2, "stopped": 1}},
        },
    }
