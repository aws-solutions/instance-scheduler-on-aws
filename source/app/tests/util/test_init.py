# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime

from instance_scheduler.util import safe_json


def test_safe_json() -> None:
    safe_json(datetime.now())
