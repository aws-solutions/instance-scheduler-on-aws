# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any, Optional

from boto3 import Session

from instance_scheduler.util import get_boto_config


def get_client_with_standard_retry(
    service_name: str, region: Optional[str] = None, session: Optional[Session] = None
) -> Any:
    aws_session = session if session is not None else Session()

    result = aws_session.client(
        service_name=service_name, region_name=region, config=get_boto_config()
    )

    return result
