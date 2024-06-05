# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import os
import uuid
from dataclasses import dataclass
from unittest.mock import patch

from instance_scheduler.ops_metrics import metrics
from instance_scheduler.ops_metrics.metrics import MetricsEnvironment


@dataclass
class MockMetricsEnviron(MetricsEnvironment):
    send_anonymous_metrics: bool = False
    anonymous_metrics_url: str = "my-metrics-url"
    solution_id: str = "my-solution-id"
    solution_version: str = "my-solution-version"
    scheduler_frequency_minutes: int = 5
    metrics_uuid: uuid.UUID = uuid.uuid4()

    def _to_env_dict(self) -> dict[str, str]:
        return {
            "SEND_METRICS": str(self.send_anonymous_metrics),
            "METRICS_URL": self.anonymous_metrics_url,
            "SOLUTION_ID": self.solution_id,
            "SOLUTION_VERSION": self.solution_version,
            "SCHEDULING_INTERVAL_MINUTES": str(self.scheduler_frequency_minutes),
            "METRICS_UUID": str(self.metrics_uuid),
        }

    def __enter__(self) -> "MockMetricsEnviron":
        self._patcher = patch.dict(os.environ, self._to_env_dict())
        self._patcher.__enter__()
        metrics._metrics_env = None  # reset caching
        return self

    def __exit__(self, exc_type: None, exc_val: None, exc_tb: None) -> None:
        self._patcher.__exit__()
        metrics._metrics_env = None  # reset caching
